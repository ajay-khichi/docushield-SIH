from docushield import face
from synth.faces import make_face, make_selfie


def test_same_person_scores_high():
    a = make_face(501)
    b = make_selfie(501, rng_seed=9001)
    assert face.demo_similarity(a, b) >= face.C.FACE_MATCH_MIN


def test_different_people_score_low():
    a = make_face(501)
    b = make_face(9999)
    assert face.demo_similarity(a, b) < face.C.FACE_MATCH_MIN


def test_auc_on_held_out_identities():
    import numpy as np
    same, diff = [], []
    for s in range(600, 650):
        a = make_face(s)
        same.append(face.demo_similarity(a, make_selfie(s, rng_seed=s * 3 + 1)))
        diff.append(face.demo_similarity(a, make_face(s + 5000)))
    same, diff = np.array(same), np.array(diff)
    auc = float((same[:, None] > diff[None, :]).mean())
    assert auc > 0.9
