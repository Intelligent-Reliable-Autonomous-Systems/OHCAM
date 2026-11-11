import numpy as np

def get_binary_entropy(prob: float | np.ndarray) -> float | np.ndarray:
    """
    Compute the binary entropy of a probability or array of probabilities.
    """
    if isinstance(prob, float):
        if prob <= 0.0 or prob >= 1.0:
            return 0.0
        return -(prob * np.log(prob) + (1 - prob) * np.log(1 - prob))
    elif isinstance(prob, np.ndarray):
        entropy = np.zeros_like(prob)
        mask = (prob > 0.0) & (prob < 1.0)
        entropy[mask] = -(prob[mask] * np.log(prob[mask]) + (1 - prob[mask]) * np.log(1 - prob[mask]))
        return entropy
    else:
        raise ValueError(f"Invalid probability: {prob}")

def softmax(x: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    """
    Softmax function.
    """
    z = np.asarray(x, dtype=np.float64) / temperature
    z = np.exp(z - np.max(z)) # shift by the max so large utilities don't overflow
    return z / np.sum(z)

