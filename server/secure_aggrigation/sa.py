import random
from sympy import mod_inverse

def polynomial(coeffs, x, prime):
    return sum([coeff * (x ** i) for i, coeff in enumerate(coeffs)]) % prime

def generate_shares(secret, threshold, num_shares, prime=2147483647):
    coeffs = [secret] + [random.randint(1, prime - 1) for _ in range(threshold - 1)]
    shares = [(i, polynomial(coeffs, i, prime)) for i in range(1, num_shares + 1)]
    return shares

def reconstruct_secret(shares, prime=2147483647):
    secret = 0
    for i, (x_i, y_i) in enumerate(shares):
        num, den = 1, 1
        for j, (x_j, _) in enumerate(shares):
            if i != j:
                num = (num * (-x_j)) % prime
                den = (den * (x_i - x_j)) % prime
        lagrange_coeff = (num * mod_inverse(den, prime)) % prime
        secret = (secret + (y_i * lagrange_coeff)) % prime
    return secret

# Simulation parameters
secret_value = 12345
threshold = 3
num_shares = 5

# Generate and distribute shares
shares = generate_shares(secret_value, threshold, num_shares)
print("Generated Shares:", shares)

# Reconstruct the secret using threshold number of shares
reconstructed_secret = reconstruct_secret(shares[:threshold])
print("Reconstructed Secret:", reconstructed_secret)

# Evaluate robustness by testing with insufficient shares
try:
    incomplete_reconstruction = reconstruct_secret(shares[:(threshold - 1)])
    print("Reconstruction with insufficient shares:", incomplete_reconstruction)
except Exception as e:
    print("Reconstruction failed due to insufficient shares, as expected.")
