import json
import os
import pytest

from accession_workflow.data import workflow


@pytest.fixture
def login_response():
    login_response = workflow.authorise()
    login_response.raise_for_status()
    return login_response


def test_authorise(login_response):
    assert login_response.status_code == 200

    access_token = login_response.json()["access_token"]

    assert len(access_token) == 1413
    assert type(access_token) is str


@pytest.fixture
def access_token(login_response):
    return login_response.json()["access_token"]


def test_run_text_recognition(access_token):
    pass

def test_get_doc_manifest(access_token):
    doc_manifest = workflow.get_doc_manifest(
        access_token=access_token,
        collection_id=2142572,
        doc_id=10223347
    )

    assert type(doc_manifest) is dict


def test_download_doc(tmp_path):
    """
    Test workflow.download_doc()

    Args:
        tmp_path (_type_): _description_
    """
    doc_id = 10223347
    doc_manifest = json.load(open("tests/manifest.json"))
    workflow.download_doc(doc_id=doc_id, doc_manifest=doc_manifest, out_path=tmp_path)

    assert os.path.exists(f"{tmp_path}/{doc_id}/0_title.jpg")
    assert os.path.exists(f"{tmp_path}/{doc_id}/0_title.xml")
