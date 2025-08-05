import numpy as np

def compute_head_mobility(landmarks_sequence):
    """
    landmarks_sequence: List of np.array, each of shape (num_landmarks, 2) or (num_landmarks, 3)
    Returns: List of frame-to-frame landmark vector differences (norms)
    """
    mobility = []
    for i in range(1, len(landmarks_sequence)):
        diff = landmarks_sequence[i] - landmarks_sequence[i-1]
        norm = np.linalg.norm(diff, axis=1).mean()  # mean movement per landmark
        mobility.append(norm)
    return mobility
