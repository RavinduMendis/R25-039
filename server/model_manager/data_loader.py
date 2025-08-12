# data_loader.py

import torch
from torchvision import datasets, transforms
from torch.utils.data import DataLoader

def load_cifar10_test_data():
    """
    Loads and prepares the CIFAR-10 test dataset.
    This function can be reused across different parts of an application.
    """
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    ])
    testset = datasets.CIFAR10(root='./data', train=False, download=True, transform=transform)
    return DataLoader(testset, batch_size=64, shuffle=False)