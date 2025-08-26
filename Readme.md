This repo is an offshoot of the Convert-a-Card project, tailored to support fast accession of material into the collections during BL office moves.
Code here consumes xml files produced from card transcription by [Transkribus](lite.transkribus.eu),
parses the xml to extract card title/author/ISBN the queries [OCLC Worldcat](https://www.worldcat.org/) to see if a matching record exists.

This repo was created by Harry Lloyd, building on earlier work by Giorgia Tolfo and Victoria Morris.

Structure  
```
├── README.md           <- The top-level README for developers using this project.  
├── data  
│   ├── processed       <- The final, canonical data sets.
│   ├── interim         <- Data in interim stages of processing.
│   └── raw             <- The original, immutable data dump.  
│  
├── notebooks           <- Jupyter notebooks.  
│  
├── reports             <- Generated analysis as HTML, PDF, LaTeX, etc.  
│   └── figures         <- Generated graphics and figures to be used in reporting  
│  
├── environment.yml     <- conda environment
│  
├── src                 <- Source code for use in this project.  
│   ├── __init__.py     <- Makes src a Python module  
│   │  
│   ├── data            <- Scripts to download or generate data  
│   │   └── oclc_api.py    <- OCLC Worldcat API queries, including using the bookops_worldcat package
│   │   └── xml_extraction.py   <- extract labelled text from xml files 
│   │   └── accession_workflow.py   <- combine use of the Transkribus API, xml extraction, the OCLC API and Streamlit for data vis
│
├── tests               <- pytest unit tests for src  
```