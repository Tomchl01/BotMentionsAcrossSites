import hashlib

def generate_hash(*args):
    combined = "|".join(str(a).strip() for a in args)
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()
