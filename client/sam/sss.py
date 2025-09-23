import torch
import numpy as np
import logging
import io
import json
from typing import Dict, Any, List
from collections import defaultdict


class _SecretSharer:
    """
    Implements a simple Shamir's Secret Sharing algorithm using numpy.
    """
    prime = 104857601  # A large prime for modular arithmetic

    @staticmethod
    def mod_inverse(a: int, m: int) -> int:
        """Computes the modular multiplicative inverse of a modulo m."""
        return pow(a, m - 2, m)

    @staticmethod
    def split_secret(secret: int, k: int, n: int) -> List[tuple[int, int]]:
        """Splits a secret into n shares, requiring k to reconstruct."""
        coeffs = [secret] + [np.random.randint(0, _SecretSharer.prime) for _ in range(k - 1)]
        shares = []
        for i in range(1, n + 1):
            y = sum(c * (i ** j) for j, c in enumerate(coeffs)) % _SecretSharer.prime
            shares.append((i, y))
        return shares

    # <<< FIX START >>>
    # The original `recover_secret` method had a flawed implementation of Lagrange interpolation.
    # This new version uses the correct formula to calculate the Lagrange basis polynomials,
    # ensuring the reconstructed integer is correct and preventing the OverflowError.
    @staticmethod
    def recover_secret(shares: List[tuple[int, int]]) -> int:
        """Reconstructs the secret from a list of shares using Lagrange interpolation."""
        if len(shares) < 2:
            raise ValueError("At least two shares are required.")

        secret = 0
        x_coords, y_coords = zip(*shares)

        for i in range(len(shares)):
            # Calculate Lagrange basis polynomial l_i(0)
            numerator = 1
            denominator = 1
            for j in range(len(shares)):
                if i != j:
                    numerator = (numerator * -x_coords[j]) % _SecretSharer.prime
                    denominator = (denominator * (x_coords[i] - x_coords[j])) % _SecretSharer.prime
            
            # Compute l_i(0) and multiply by y_i
            term = (y_coords[i] * numerator * _SecretSharer.mod_inverse(denominator, _SecretSharer.prime)) % _SecretSharer.prime
            secret = (secret + term) % _SecretSharer.prime

        return int(secret)
    # <<< FIX END >>>


class SecretSharing:
    """
    Handles splitting and reconstructing model updates using a chunking mechanism.
    """
    CHUNK_SIZE = 3  # number of bytes per chunk

    def __init__(self, num_shares: int, threshold: int):
        if threshold > num_shares:
            raise ValueError("Threshold cannot be greater than the number of shares.")
        self.num_shares = num_shares
        self.threshold = threshold
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(
            f"SecretSharing initialized with {num_shares} shares, "
            f"a threshold of {threshold}, and a chunk size of {self.CHUNK_SIZE} bytes."
        )

    def split_model(self, state_dict: Dict[str, Any]) -> List[bytes]:
        """
        Serializes a model, breaks it into chunks, creates secret shares for each chunk,
        and bundles them into a single JSON payload.
        """
        buffer = io.BytesIO()
        torch.save(state_dict, buffer)
        model_bytes = buffer.getvalue()
        original_length = len(model_bytes)

        all_shares_by_server = [[] for _ in range(self.num_shares)]

        for chunk_index, i in enumerate(range(0, original_length, self.CHUNK_SIZE)):
            chunk = model_bytes[i:i + self.CHUNK_SIZE]
            chunk_int = int.from_bytes(chunk, 'big')

            if chunk_int >= _SecretSharer.prime:
                raise ValueError(f"Chunk {chunk_index} is too large for the SSS prime field.")

            shares_for_chunk = _SecretSharer.split_secret(chunk_int, self.threshold, self.num_shares)

            for share_idx, share_tuple in enumerate(shares_for_chunk):
                payload = {"c": chunk_index, "s": list(share_tuple)}
                all_shares_by_server[share_idx].append(payload)

        final_payloads = []
        for server_shares in all_shares_by_server:
            bundle = {"l": original_length, "d": server_shares}
            final_payloads.append(json.dumps(bundle).encode('utf-8'))

        self.logger.info(
            f"Model of size {original_length} bytes split into {self.num_shares} bundles."
        )
        return final_payloads

    def reconstruct_model(self, shares_payloads: List[bytes]) -> Dict[str, Any]:
        """
        Reconstructs the original model from a list of share bundles.
        """
        if len(shares_payloads) < self.threshold:
            raise ValueError(
                f"Insufficient share bundles provided. Required at least {self.threshold}, got {len(shares_payloads)}."
            )

        grouped_shares_by_chunk = defaultdict(list)
        original_length = None

        for share_bundle_bytes in shares_payloads:
            try:
                bundle = json.loads(share_bundle_bytes.decode('utf-8'))
                if original_length is None:
                    original_length = bundle["l"]
                
                for payload in bundle["d"]:
                    chunk_index = payload["c"]
                    share_tuple = tuple(payload["s"])
                    grouped_shares_by_chunk[chunk_index].append(share_tuple)

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                self.logger.warning(f"Skipping invalid share bundle: {e}")
                continue

        if original_length is None:
            raise RuntimeError("Failed to find original model length. Reconstruction aborted.")

        reconstructed_chunk_ints = {}
        total_expected_chunks = (original_length + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE

        for chunk_index, chunk_shares in grouped_shares_by_chunk.items():
            if len(chunk_shares) >= self.threshold:
                reconstructed_int = _SecretSharer.recover_secret(chunk_shares)
                reconstructed_chunk_ints[chunk_index] = reconstructed_int

        if len(reconstructed_chunk_ints) != total_expected_chunks:
             raise RuntimeError(f"Failed to reconstruct all chunks. Reconstructed {len(reconstructed_chunk_ints)} out of {total_expected_chunks} expected chunks.")

        num_full_chunks = original_length // self.CHUNK_SIZE
        size_of_last_chunk = original_length % self.CHUNK_SIZE
        
        byte_pieces = []
        for i in sorted(reconstructed_chunk_ints.keys()):
            chunk_int = reconstructed_chunk_ints[i]
            if i < num_full_chunks:
                byte_pieces.append(chunk_int.to_bytes(self.CHUNK_SIZE, 'big'))
            else:
                if size_of_last_chunk > 0:
                    byte_pieces.append(chunk_int.to_bytes(size_of_last_chunk, 'big'))

        final_bytes = b"".join(byte_pieces)

        if len(final_bytes) != original_length:
            raise RuntimeError(
                f"Reconstruction failed: Mismatch between final byte length ({len(final_bytes)}) "
                f"and original length ({original_length})."
            )

        try:
            buffer = io.BytesIO(final_bytes)
            reconstructed_state_dict = torch.load(buffer, map_location="cpu", weights_only=False)
            self.logger.info("Model reconstructed successfully from shares.")
            return reconstructed_state_dict
        except Exception as e:
            self.logger.error(f"Error deserializing reconstructed model: {e}", exc_info=True)
            raise RuntimeError("Failed to deserialize the final reconstructed model.")