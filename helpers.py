import subprocess
import os
from pydub import AudioSegment
from hashlib import sha1
from time import time
from typing import List, Tuple, Dict
import numpy as np
import audioop
# import wavio
import fnmatch

def get_data(file: str):
    output_file = downsampling(file)
    # data = wavio.read(output_file.replace('.mp3', '.wav')).data
    data, framerate, unique_hash = read(output_file)
    os.remove(output_file)
    # os.remove(output_file.replace('.mp3', '.wav'))
    return data, framerate, unique_hash

def downsampling(file: str):
    file = file.replace('/', '\\')
    file_name = file.split('\\')
    output_path = '.\\' + file_name[-1]
    try:
        os.remove(output_path)
    except FileNotFoundError:
        pass
    subprocess.call(f'ffmpeg -ss 0 -i "{file}" -ar 16000 -ac 1 -t 62 "{output_path}"')
    # AudioSegment.from_mp3(output_path).export(output_path.replace('.mp3', '.wav'), format='wav')
    return output_path


def unique_hash(file_path: str, block_size: int = 2**20) -> str:
    hash = sha1()
    with open(file_path, "rb") as f:
        while True:
            buf = f.read(block_size)
            if not buf:
                break
            hash.update(buf)
    return hash.hexdigest().upper()

def find_files(path: str, extensions: List[str]) -> List[Tuple[str, str]]:
    """
    Get all files that meet the specified extensions.

    :param path: path to a directory with audio files.
    :param extensions: file extensions to look for.
    :return: a list of tuples with file name and its extension.
    """
    # Allow both with ".mp3" and without "mp3" to be used for extensions
    # [('filepath', 'extension'), (), ()]
    extensions = [e.replace(".", "") for e in extensions]

    results = []
    for dirpath, dirnames, files in os.walk(path):
        for extension in extensions:
            for f in fnmatch.filter(files, f"*.{extension}"):
                # p = '/path/to/file/file.mp3'
                p = os.path.join(dirpath, f)
                results.append((p, extension))
    return results

def read(file_name: str, limit: int = 60) -> Tuple[List[List[int]], int, str]:
    try:
        audiofile = AudioSegment.from_file(file_name)

        if limit:
            audiofile = audiofile[:limit * 1000]

        data = np.fromstring(audiofile.raw_data, np.int16)

        channels = []
        for chn in range(audiofile.channels):
            channels.append(data[chn::audiofile.channels])

        audiofile.frame_rate
    except audioop.error:
        # _, _, audiofile = wavio.readwav(file_name)

        # if limit:
        #     audiofile = audiofile[:limit * 1000]

        # audiofile = audiofile.T
        # audiofile = audiofile.astype(np.int16)

        # channels = []
        # for chn in audiofile:
        #     channels.append(chn)
        return

    return channels, audiofile.frame_rate, unique_hash(file_name)