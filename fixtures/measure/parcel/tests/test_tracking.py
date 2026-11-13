from parcel.tracking import is_valid, new_code


def test_new_code_is_valid():
    assert is_valid(new_code(42))


def test_one_wrong_digit_is_caught():
    code = new_code(42)
    wrong = code[:5] + ("0" if code[5] != "0" else "1") + code[6:]
    assert not is_valid(wrong)
