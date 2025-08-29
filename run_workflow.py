import asyncio
from datetime import datetime
import os
import time

import bookops_worldcat as bw

from accession_workflow.data import workflow
from cfg import COL_ID, DOC_ID, PRINT_M1_ID

print("\nInitialising loggers")
today = datetime.now().strftime("%y%m%d")
complete_log = f"logs\\{today}_tag_removal_debug_async.log"
progress_log = f"logs\\{today}_tag_removal_progress_async.log"
error_log = f"logs\\{today}_tag_removal_error_async.log"

workflow.init_loggers(complete_path=complete_log, progress_path=progress_log, error_path=error_log)

login_response = workflow.authorise()
login_response.raise_for_status()

print(f"Login successful. Status code: {login_response.status_code}")
access_token = login_response.json()["access_token"]

## Running the transcription
ATR = False
if ATR:
    # Start text recognition
    job_info = workflow.run_text_recognition(
        access_token=access_token,
        collection_id=COL_ID,
        doc_id=DOC_ID,
        model_id=PRINT_M1_ID,
        pages="all"  # or specific pages like "1,2,3"
    )

    if job_info and 'jobId' in job_info:
        job_id = job_info['jobId']

        # Check job status

        time.sleep(5)  # Wait a bit before checking status

        status = workflow.check_job_status(
            access_token=access_token,
            collection_id=DOC_ID,
            job_id=job_id
        )

        print(status)

## DL outputs
DL = True
if DL:
    workflow.download_document(access_token=access_token, collection_id=COL_ID, doc_id=DOC_ID)

PARSE_XML = True
if PARSE_XML:
    # Extract titles/ISBNs
    xml_roots = workflow.load_xmls(f"data/raw/{DOC_ID}/*.xml")
    lines = workflow.extract_lines(xml_roots)
    bib_info = workflow.extract_bib_info(lines)
    print(f"Extracted bib info: {bib_info}")

OCLC = True
if OCLC:
    token = bw.WorldcatAccessToken(
        key=os.environ["OCLC_CLIENT_KEY"],
        secret=os.environ["OCLC_CLIENT_SECRET"],
        scopes="WorldCatMetadataAPI",
        agent="ConvertACard/1.0"
    )

    run_id = "0001"
    asyncio.run(workflow.oclc_record_fetch(
        work_bib_info=bib_info,
        brief_out="data/processed/accession_test_brief_bibs.p",
        full_out="data/processed/accession_test_full_bibs.p",
        run_id=run_id,
        token=token
    ))

# Make results available for ST app
# St app should be used side by side with Record Manager, so this automated part ends there