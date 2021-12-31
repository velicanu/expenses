import multiprocessing as mp
import os
import tempfile

from common import get_files, get_log
from detect import identify_file
from extract import extract
from ingest import ingest
from parse import parse
from standardize import standardize
from utils import make_dirs

log = get_log(__file__)


def get_filename_without_extension(filename):
    return os.path.basename(filename).split(".")[0]


def get_pipeline_files(raw_dir, extracted_dir, parsed_dir, standardized_dir):
    """
    yields file names corresponding to the raw, extracted, parsed, standardized
    intermediate steps pf the pipeline
    """
    suffix = ".json"
    for raw_file in [f for f in get_files(raw_dir) if identify_file(f)]:
        filestem = get_filename_without_extension(raw_file)
        extracted_file = os.path.join(extracted_dir, filestem + suffix)
        parsed_file = os.path.join(parsed_dir, filestem + suffix)
        standardized_file = os.path.join(standardized_dir, filestem + suffix)
        yield raw_file, extracted_file, parsed_file, standardized_file


def _etl(raw, extracted, parsed, standardized):
    extract(raw, extracted)
    parse(extracted, parsed)
    standardize(parsed, standardized)


def run(data_dir):
    """
    Run the pipeline, intermediate files go into
    data/extracted, data/parsed, and data/standardized
    which is ingested into ./expenses.db
    """

    cores = mp.cpu_count()
    pool = mp.Pool(cores)
    jobs = []

    raw_dir = os.path.join(data_dir, "raw")
    extracted_dir = os.path.join(data_dir, "extracted")
    parsed_dir = os.path.join(data_dir, "parsed")
    standardized_dir = os.path.join(data_dir, "standardized")
    make_dirs([raw_dir, extracted_dir, parsed_dir, standardized_dir])

    if len(os.listdir(raw_dir)) == 0:
        return False

    with tempfile.TemporaryDirectory() as tmp_standardized_dir:
        for raw, extracted, parsed, standardized in get_pipeline_files(
            raw_dir, extracted_dir, parsed_dir, tmp_standardized_dir
        ):
            jobs.append(pool.apply_async(_etl, (raw, extracted, parsed, standardized)))

        [job.get() for job in jobs]
        # TODO: hardcoded expenses tablename and expenses.db
        ingest(
            get_files(tmp_standardized_dir),
            "expenses",
            os.path.join(data_dir, "expenses.db"),
        )
        for file_ in os.listdir(tmp_standardized_dir):
            os.replace(
                os.path.join(tmp_standardized_dir, file_),
                os.path.join(standardized_dir, file_),
            )
    return True


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.realpath(__file__))
    run(os.path.join(script_dir, "..", "data"))
