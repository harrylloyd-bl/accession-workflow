# TKB API access
import asyncio
import glob
import logging
import pickle
import os
import re
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
import requests
from tqdm import tqdm
import bookops_worldcat as bw
from TranskribusPyClient.src.TranskribusPyClient import client

from src.data.oclc_api import process_queue, cac_search_kwargs
from cfg import COL_ID, DOC_ID, PRINT_M1_ID

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
        # Step 2: Start text recognition job
        recognition_url = f"{base_url}/recognition/htr"

        # Parameters for the recognition job
        recognition_params = {
            "colId": collection_id,  # the collection id
            "id": doc_id,  # the document id
            "pages": pages,  # "all" or specific page numbers
            "modelId": model_id,
            "doWordSeg": "true",  # Enable word segmentation
            "doLineSeg": "false",  # Usually false if using existing layout
            "doPolygonToBaseline": "false"
        }

        # Start the recognition job
        recognition_response = session.post(
            recognition_url,
            params=recognition_params,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        recognition_response.raise_for_status()

        # Parse the response
        job_info = recognition_response.json()
        job_id = job_info.get('jobId')

        print(f"Text recognition job started successfully!")
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


def download_document(access_token, collection_id, doc_id):
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
        get_doc_url = f"{base_url}/collections/{collection_id}/{doc_id}/fulldoc"
        doc_response = session.get(get_doc_url, headers=headers)
        doc_contents = doc_response.json()
        n = len(doc_contents["pageList"]["pages"])

        # TODO link title and ISBN pages
        print("Downloading images and xmls")
        for i, page in tqdm(enumerate(doc_contents["pageList"]["pages"]), total=n):
            if i / 2 == float(i // 2):
                suffix = "title"
            else:
                suffix = "isbn"

            work = (int(page['pageNr']) - 1) // 2

            img_resp = requests.get(page["url"])
            xml_resp = requests.get(page['tsList']['transcripts'][0]['url'])
            if not os.path.exists(f"data/raw/{doc_id}"):
                os.mkdir(f"data/raw/{doc_id}")
            with open(f"data/raw/{doc_id}/{work}_{suffix}.jpg", "wb") as f:
                f.write(img_resp.content)
            with open(f"data/raw/{doc_id}/{work}_{suffix}.xml", "wb") as f:
                f.write(xml_resp.content)

        print(f"Images and xml downloaded for {len(doc_contents['pageList']['pages']) // 2} works")

        return doc_response.raise_for_status()

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
        page_lines[id] = [l for l in lines if l]

    return page_lines


def extract_bib_info(page_lines: dict[str: list[str]]):
    """
    Extract bibliographic info from transcribed book pages
    @param page_lines:
    @return:
    """
    isbn_regex = re.compile("ISBN\s(?P<ISBN>[0-9\-\s]+)")
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
                    clean_isbn = ISBN.replace("-", "").replace(" ", "")
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


async def oclc_record_fetch(work_bib_info, out_path):

    brief_bibs = {}
    full_bibs = {}
    full_bibs = {k: [] for k in full_bibs}

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
                process_queue(
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

        global run_id
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
        pickle.dump(brief_bibs, open(out_path, "wb"))


if __name__ == "__main__":
    login_response = authorise()
    login_response.raise_for_status()

    print(f"Login successful. Status code: {login_response.status_code}")
    access_token = login_response.json()["access_token"]

    ## Running the transcription
    ATR = False
    if ATR:
        # Start text recognition
        job_info = run_text_recognition(
            access_token=access_token,
            collection_id=DOC_ID,
            model_id=PRINT_M1_ID,
            pages="all"  # or specific pages like "1,2,3"
        )

        if job_info and 'jobId' in job_info:
            job_id = job_info['jobId']

            # Check job status
            import time

            time.sleep(5)  # Wait a bit before checking status

            status = check_job_status(
                access_token=access_token,
                collection_id=DOC_ID,
                job_id=job_id
            )

    ## DL outputs
    DL = False
    if DL:
        download_document(access_token=access_token, collection_id=COL_ID, doc_id=DOC_ID)

    # Extract titles/ISBNs
    xml_roots = load_xmls(f"data/raw/{DOC_ID}/*.xml")
    lines = extract_lines(xml_roots)
    bib_info = extract_bib_info(lines)
    print(bib_info)

    # Query OCLC
    client_id = os.environ["CLIENT_ID"]
    client_secret = os.environ["CLIENT_SECRET"]

    # token = bw.WorldcatAccessToken(
    #     key=client_id,
    #     secret=client_secret,
    #     scopes="WorldCatMetadataAPI",
    #     agent="ConvertACard/1.0"
    # )

    # asyncio.run(oclc_record_fetch(bib_info, "data/processed/accession_test_brief_bibs.p"))

    # Make results available for ST app
    # St app should be used side by side with Record Manager, so this automated part ends there