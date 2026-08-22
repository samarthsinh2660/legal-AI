from evals.dataset import DEFAULT_DATASET, EvalQuestion, load_questions
from legal_ai.knowledge.static.db import get_connection


def test_loads_the_default_dataset():
    questions = load_questions()
    assert len(questions) >= 50
    assert all(isinstance(q, EvalQuestion) for q in questions)


def test_every_question_has_text_and_at_least_one_expected_id():
    for question in load_questions():
        assert question.question.strip(), f"{question.id} has no question text"
        assert question.expected, f"{question.id} has no expected answer"


def test_question_ids_are_unique():
    ids = [q.id for q in load_questions()]
    assert len(ids) == len(set(ids))


def test_expected_ids_all_resolve_to_real_documents():
    # The single most important test in the harness. An expected id that
    # does not exist can never be retrieved, so the benchmark would report
    # a permanent, unfixable failure and blame retrieval for it.
    expected = {doc_id for q in load_questions() for doc_id in q.expected}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT document_id FROM documents WHERE document_id = ANY(%s)",
                (list(expected),),
            )
            found = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()
    assert expected - found == set(), f"dataset references missing documents: {expected - found}"


def test_dataset_file_is_where_the_loader_expects():
    assert DEFAULT_DATASET.exists()
