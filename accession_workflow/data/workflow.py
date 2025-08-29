# TKB API access
import asyncio
import glob
import logging
import pickle
import os
import re
import time
from typing import Any
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
import requests
from tqdm import tqdm
import bookops_worldcat as bw

from accession_workflow.data.oclc_api import process_queue, cac_search_kwargs

load_dotenv()

def authorise():
    auth_url = "https://account.readcoop.eu/auth/realms/readcoop/protocol/openid-connect/token"
    data = {
        "grant_type": "password",
        "username": os.environ["TKB_USERNAME"],
        "password": os.environ["TKB_PASSWORD"],
        "client_id": "processing-api-client"
    }

    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    resp = requests.post(auth_url, data=data, headers=headers)
    return resp

# Retrieve the ColID for DocScan - Uploads
# collection_ids = requests.get("https://transkribus.eu/TrpServer/rest/collections", headers=headers)
# ColID is 2142572, stored in cfg.py


def run_text_recognition(access_token, collection_id, doc_id, model_id, pages="all"):
    """
    Run text recognition on a Transkribus collection

    Args:
        access_token (str): Tkb access token
        collection_id (int): ID of the collection to process
        model_id (int): ID of the HTR model to use
        pages (str): Pages to process (default: "all")

    Returns:
        dict: API response containing job information
    """

    # Base URL for Transkribus API
    base_url = "https://transkribus.eu/TrpServer/rest"
    session = requests.Session()

    try:
        # Start text recognition job
        headers = {"Authorization": f"Bearer {access_token}",
                   "Content-Type": "application/json"}

        recognition_endpoint = f"{base_url}/pylaia/{collection_id}/{model_id}/recognition"

        # Parameters for the recognition job
        recognition_params = {
            "id": doc_id,  # the document id
            "doLinePolygonSimplification": True,
            "keepOriginalLinePolygons": False
            # "doWordSeg": "true",  # Enable word segmentation
        }

        data = {"pages": pages}
        # Start the recognition job
        recognition_response = session.post(
            recognition_endpoint,
            params=recognition_params,
            headers=headers,
            data=data
        )
        recognition_response.raise_for_status()

        # Parse the response
        job_info = recognition_response.json()
        job_id = job_info.get('jobId')

        print("Text recognition job started successfully!")
        print(f"Job ID: {job_id}")
        print(f"Collection ID: {collection_id}")
        print(f"Model ID: {model_id}")

        return job_info

    except requests.exceptions.RequestException as e:
        print(f"Error occurred: {e}")
        if hasattr(e.response, 'text'):
            print(f"Response text: {e.response.text}")
        return None


def check_job_status(access_token, collection_id, job_id):
    """
    Check the status of a recognition job

    Args:
        access_token (str): Tkb access token
        collection_id (int): ID of the collection
        job_id (str): ID of the job to check

    Returns:
        dict: Job status information
    """
    base_url = "https://transkribus.eu/TrpServer/rest"
    session = requests.Session()

    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        # Check job status
        status_url = f"{base_url}/jobs/{job_id}"
        status_response = session.get(status_url, headers=headers)
        status_response.raise_for_status()

        job_status = status_response.json()

        print(f"Job Status: {job_status.get('state', 'Unknown')}")
        print(f"Progress: {job_status.get('progress', 'N/A')}%")

        return job_status

    except requests.exceptions.RequestException as e:
        print(f"Error checking job status: {e}")
        return None


def get_doc_manifest(access_token: str, collection_id: int, doc_id: int) -> dict[any, any]|None:
    """
    Download the manifest for a document
    This contains urls for all xml/jpgs which can then be downloaded separately

    Args:
        access_token (str): Tkb access token
        collection_id (int): ID of the collection
        doc_id (str): ID of the doc to download

    Returns:
        doc_manifest: Document manifest
    """
    base_url = "https://transkribus.eu/TrpServer/rest"
    session = requests.Session()

    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        # Check job status
        get_doc_url = f"{base_url}/collections/{collection_id}/{doc_id}/fulldoc"
        doc_response = session.get(get_doc_url, headers=headers)
        doc_response.raise_for_status()
        print(f"Get doc info successful. Status code: {doc_response.status_code}")
        doc_manifest = doc_response.json()

        return doc_manifest
    
    except requests.exceptions.RequestException as e:
        print(f"Error downloading doc manifest: {e}")
        return None
    

def download_doc(doc_id: int, doc_manifest: dict[Any, Any], out_path: str|os.PathLike) -> None:
    """
    Download a complete document

    Args:
        doc_manifest (dict): The manifest for a document, containing jpg/xml urls
        doc_id (str): ID of the doc to download

    Returns:
        None
    """
    try:
        n = len(doc_manifest["pageList"]["pages"])

        # TODO link title and ISBN pages
        print("Downloading images and xmls")
        for i, page in tqdm(enumerate(doc_manifest["pageList"]["pages"]), total=n):
            if i / 2 == float(i // 2):
                suffix = "title"
            else:
                suffix = "isbn"

            work = (int(page['pageNr']) - 1) // 2

            img_resp = requests.get(page["url"])
            xml_resp = requests.get(page['tsList']['transcripts'][0]['url'])
            if not os.path.exists(f"{out_path}/{doc_id}"):
                os.mkdir(f"{out_path}/{doc_id}")
            with open(f"{out_path}/{doc_id}/{work}_{suffix}.jpg", "wb") as f:
                f.write(img_resp.content)
            with open(f"{out_path}/{doc_id}/{work}_{suffix}.xml", "wb") as f:
                f.write(xml_resp.content)

        print(f"Images and xml downloaded for {len(doc_manifest['pageList']['pages']) // 2} works")

    except requests.exceptions.RequestException as e:
        print(f"Error downloading doc: {e}")
        return None


def load_xmls(xml_path: str) -> dict[str: ET]:
    xmls = glob.glob(xml_path)
    xml_roots = {}
    for file in xmls:
        page_id = os.path.basename(file)
        file = os.fsdecode(file)
        attempts = 0
        while attempts < 3:
            try:
                tree = ET.parse(file)
                break
            except FileNotFoundError:
                attempts += 1
                continue
        else:
            raise FileNotFoundError(f"Failed to connect to: {file}")
        root = tree.getroot()
        xml_roots[page_id] = root

    return xml_roots


def extract_lines(xml_roots: dict[str: ET]) -> dict[str: list[str]]:
    page_lines = {}
    for id, root in xml_roots.items():
        lines = []
        text_regions = [x for x in root[1] if len(x) > 2]  # Empty Text Regions Removed

        for text_region in text_regions:
            text_lines = text_region[1:-1]  # Skip coordinate data in first child
            for text_line in text_lines:
                lines.append(text_line[-1][0].text)  # Text equivalent for line
        page_lines[id] = [line for line in lines if line]

    return page_lines


def extract_bib_info(page_lines: dict[str: list[str]]):
    """
    Extract bibliographic info from transcribed book pages
    @param page_lines:
    @return:
    """
    isbn_regex = re.compile(r"ISBN\s(?P<ISBN>[0-9\-\s\.]+)")
    work_bib_info = {page_nr.split("_")[0]: {} for page_nr, _ in page_lines.items()}
    # TODO at the moment the title page transcription is bad due to the large font sizes
    # Just use ISBN for now

    for page_nr, lines in page_lines.items():
        if "isbn" in page_nr:
            page_nr = page_nr.split("_")[0]
            ISBN = None
            for line in lines:
                match = isbn_regex.search(line)
                if match:
                    ISBN = match.group("ISBN")
                    clean_isbn = ISBN.replace("-", "").replace(" ", "").replace(".", "")
                    work_bib_info[page_nr]["ISBN"] = clean_isbn

        elif "title" in page_nr:
            page_nr = page_nr.split("_")[0]
            if len(lines) == 2:
                title, author = lines
                work_bib_info[page_nr]["title"] = title
                work_bib_info[page_nr]["author"] = author
            elif len(lines) > 2:
                title = " ".join(lines[:-1])
                author = lines[-1]
                work_bib_info[page_nr]["title"] = title
                work_bib_info[page_nr]["author"] = author

    return work_bib_info


async def oclc_record_fetch(work_bib_info, brief_out: str|os.PathLike, full_out: str|os.PathLike, run_id: str, token: bw.WorldcatAccessToken) -> None:
    """
    Process bib info extracted from book pages by querying for brief bibs
    Then querying for OCLC numbers based on brief bibs
    """
    brief_bibs = {k: {} for k in work_bib_info}
    full_bibs = {k: [] for k in work_bib_info}

    async with bw.AsyncMetadataSession(authorization=token, headers={"User-Agent": "Convert-a-Card/1.0"}) as session:

        queue = asyncio.Queue()
        for work, bib_info in work_bib_info.items():

            title, author, isbn = bib_info["title"], bib_info["author"], bib_info["ISBN"]
            await queue.put((work, title, author, isbn))

        print("Creating workers")
        print("brief bib search API call progress:")
        tracker = tqdm(total=queue.qsize())

        tasks = []
        n_workers = 50  # 25 gave no errors for 5000 records

        for i in range(n_workers):  # create workers
            task = asyncio.create_task(
                process_queue(  # Queue also processes the full bib calls
                    queue=queue,
                    name=f'worker-{i}',
                    session=session,
                    search_kwargs=cac_search_kwargs,
                    brief_bibs_out=brief_bibs,
                    full_bibs_out=full_bibs,
                    tracker=tracker
                )
            )

            tasks.append(task)

        t0 = time.perf_counter()
        logging.info(f"{run_id} OCLC query queue joined")

        await queue.join()

        t1 = time.perf_counter()
        logging.info(f"{run_id} OCLC query queue complete - elapsed: {t1 - t0}")

        for task in tasks:
            task.cancel()

        # await asyncio.gather(*tasks, return_exceptions=True)

        # records_df["brief_bibs"] = brief_bibs
        # records_df["worldcat_matches"] = full_bibs
        pickle.dump(brief_bibs, open(brief_out, "wb"))
        pickle.dump(full_bibs, open(full_out, "wb"))


def init_loggers(complete_path: str|os.PathLike, progress_path: str|os.PathLike, error_path: str|os.PathLike) -> None:
    """
    Initialise loggers for the workflow. This is mainly to track the async OCLC calls.
    Args:
        complete_path: str|os.Pathlike
        progress_path: str|os.Pathlike
        error_path: str|os.Pathlike

    Returns: None

    """
    logging.basicConfig(filename=complete_path,
                        format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                        datefmt='%m-%d %H:%M',
                        encoding='utf-8',
                        level=logging.DEBUG)

    # All logging statements go to complete_log, only logging.info statements go to progress_log
    progress = logging.FileHandler(filename=progress_path)
    progress.setLevel(logging.INFO)
    prog_formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s', datefmt='%m-%d %H:%M')
    progress.setFormatter(prog_formatter)
    logging.getLogger("").addHandler(progress)

    error = logging.FileHandler(filename=error_path)
    error.setLevel(logging.ERROR)
    err_formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s', datefmt='%m-%d %H:%M')
    error.setFormatter(err_formatter)
    logging.getLogger("").addHandler(error)

    return None
