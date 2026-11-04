import hashlib
import pytest
from services import rng

@pytest.fixture
def DrawResult_struct():
    return rng.create_draw(6, 49)

@pytest.fixture()
def DrawNumbers(DrawResult_struct):
    numbers = rng.draw(bytes.fromhex(DrawResult_struct.seed_hex), 6, 49)
    return numbers

def test_create_draw_is_commitment_valid(DrawResult_struct):
    assert DrawResult_struct.commitment == hashlib.sha256(bytes.fromhex(DrawResult_struct.seed_hex)).hexdigest()

def test_create_draw_is_hex_len_64(DrawResult_struct):
    assert len(DrawResult_struct.seed_hex) == 64

def test_create_draw_numbers_match_draw(DrawResult_struct, DrawNumbers):
    assert DrawNumbers == DrawResult_struct.numbers

def test_draw_exception_with_invalid_seed_len():
    with pytest.raises(rng.DrawError, match="32 bajty"):
        rng.draw(b"short", 6, 49)

def test_draw_exception_with_invalid_k_val(DrawResult_struct):
    with pytest.raises(rng.DrawError, match="1-max_number"):
        rng.draw(bytes.fromhex(DrawResult_struct.seed_hex), 50, 49)

def test_draw_exception_with_invalid_maxnumber_val(DrawResult_struct):
    with pytest.raises(rng.DrawError, match="max_number"):
        rng.draw(bytes.fromhex(DrawResult_struct.seed_hex), 6, 256)

def test_draw_is_lotto_nums_in_valid_range(DrawResult_struct, DrawNumbers):
    for i in DrawNumbers:
        assert 0 < i <= 49

def test_draw_is_lotto_nums_distinct_vals(DrawNumbers):
    assert len(set(DrawNumbers)) == len(DrawNumbers) == 6

def test_verify_seed_hash_with_commitment_valid_vals(DrawResult_struct, DrawNumbers):
    assert rng.verify(DrawResult_struct.commitment, DrawResult_struct.seed_hex, 6, 49, DrawNumbers)

def test_verify_seed_hash_with_commitment_modified_numbers(DrawResult_struct,DrawNumbers):
    tampered = DrawNumbers.copy()
    tampered[0], tampered[1] = tampered[1], tampered[0]
    assert not rng.verify(DrawResult_struct.commitment, DrawResult_struct.seed_hex, 6, 49, tampered)

def test_verify_seed_hash_with_commitment_invalid_seed_hex(DrawResult_struct, DrawNumbers):
    assert not rng.verify(DrawResult_struct.commitment, DrawResult_struct.seed_hex + "4f", 6, 49, DrawNumbers)

def test_verify_seed_hash_with_invalid_commitment(DrawResult_struct, DrawNumbers):
    assert not rng.verify("00" * 32, DrawResult_struct.seed_hex, 6, 49, DrawNumbers)

def test_verify_exception_with_invalid_hex(DrawResult_struct, DrawNumbers):
    with pytest.raises(rng.DrawError, match="nie jest"):
        rng.verify(DrawResult_struct.commitment, "abc", 6, 49, DrawNumbers)



