"""Callbacks."""


def delete_files():
    for filename in st.session_state.delete_files:
        os.remove(filename)
    st.session_state.delete_files = set()


def save_files_to_disk(files, data_dir):
    success = []
    failed = []
    for file_ in files:
        status, msg = save_file_if_valid(file_, data_dir)
        if status == "success":
            success.append(msg)
        else:
            failed.append(msg)

    if success:
        status_info = st.success("Saved: " + " ".join(success))
        run(data_dir)
    if failed:
        status_info = st.error("Failed: " + " ".join(failed))

    # this key increment clears the upload dialog box after clicking upload
    st.session_state.file_uploader_key += 1
    clear(streamlit_object=status_info, seconds=2)
