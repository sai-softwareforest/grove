"""Size checks made before a box is priced."""

MAX_SIDE_CM = 150


def check_size(length_cm: float, width_cm: float, height_cm: float) -> None:
    longest = max(length_cm, width_cm, height_cm)
    if longest > MAX_SIDE_CM:
        raise ValueError(f"the longest side is {longest} cm; the limit is {MAX_SIDE_CM} cm")
