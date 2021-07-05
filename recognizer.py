import multiprocessing
from typing import Tuple, List, Dict
from database_handler.mysql_database import MySQLDatabase
from time import time
import numpy as np
from itertools import groupby
from fingerprint import fingerprint
import sys, os
import traceback
import helpers
from configuration import (TOPN, DEFAULT_FS, SONG_NAME, FIELD_TOTAL_HASHES, DEFAULT_WINDOW_SIZE, DEFAULT_OVERLAP_RATIO,
                            SONG_ID, INPUT_HASHES, FINGERPRINTED_HASHES, HASHES_MATCHED, INPUT_CONFIDENCE, FINGERPRINTED_CONFIDENCE,
                            OFFSET, OFFSET_SECS, FIELD_FILE_SHA1)

def generate_fingerprints(samples: List[int], Fs=DEFAULT_FS) -> Tuple[List[Tuple[str, int]], float]:
        t = time()
        hashes = fingerprint(samples, Fs=Fs)
        fingerprint_time = time() - t
        return hashes, fingerprint_time

def find_matches(hashes: List[Tuple[str, int]], db: 'MySQLDatabase') -> Tuple[List[Tuple[int, int]], Dict[str, int], float]:
        """
        Finds the corresponding matches on the fingerprinted audios for the given hashes.

        :param hashes: list of tuples for hashes and their corresponding offsets
        :return: a tuple containing the matches found against the db, a dictionary which counts the different
         hashes matched for each song (with the song id as key), and the time that the query took.

        """
        t = time()
        matches, dedup_hashes = db.return_matches(hashes)
        query_time = time() - t

        return matches, dedup_hashes, query_time

def align_matches(matches: List[Tuple[int, int]], dedup_hashes: Dict[str, int], queried_hashes: int,
                      db: 'MySQLDatabase', topn: int = TOPN) -> List[Dict[str, any]]:

        # count offset occurrences per song and keep only the maximum ones.
        sorted_matches = sorted(matches, key=lambda m: (m[0], m[1]))
        counts = [(*key, len(list(group))) for key, group in groupby(sorted_matches, key=lambda m: (m[0], m[1]))]
        songs_matches = sorted(
            [max(list(group), key=lambda g: g[2]) for key, group in groupby(counts, key=lambda count: count[0])],
            key=lambda count: count[2], reverse=True
        )

        songs_result = []
        for song_id, offset, _ in songs_matches[0:topn]:  # consider topn elements in the result
            song = db.get_song_by_id(song_id)

            song_name = song.get(SONG_NAME, None)
            song_hashes = song.get(FIELD_TOTAL_HASHES, None)
            nseconds = round(float(offset) / DEFAULT_FS * DEFAULT_WINDOW_SIZE * DEFAULT_OVERLAP_RATIO, 5)
            hashes_matched = dedup_hashes[song_id]

            song = {
                SONG_ID: song_id,
                SONG_NAME: song_name.encode("utf8"),
                INPUT_HASHES: queried_hashes,
                FINGERPRINTED_HASHES: song_hashes,
                HASHES_MATCHED: hashes_matched,
                # Percentage regarding hashes matched vs hashes from the input.
                INPUT_CONFIDENCE: round(hashes_matched / queried_hashes, 2),
                # Percentage regarding hashes matched vs hashes fingerprinted in the db.
                FINGERPRINTED_CONFIDENCE: round(hashes_matched / song_hashes, 2),
                OFFSET: offset,
                OFFSET_SECS: nseconds,
                FIELD_FILE_SHA1: song.get(FIELD_FILE_SHA1, None).encode("utf8")
            }

            songs_result.append(song)

        return songs_result

def get_file_fingerprints(file_name: str, limit: int, print_output: bool = False):
        channels, fs, file_hash = helpers.read(file_name, limit)
        fingerprints = set()
        channel_amount = len(channels)
        for channeln, channel in enumerate(channels, start=1):
            if print_output:
                print(f"Fingerprinting channel {channeln}/{channel_amount} for {file_name}")

            hashes = fingerprint(channel, Fs=fs)

            if print_output:
                print(f"Finished channel {channeln}/{channel_amount} for {file_name}")

            fingerprints |= set(hashes)

        return fingerprints, file_hash

def _fingerprint_worker(arguments):
        # Pool.imap sends arguments as tuples so we have to unpack
        # them ourself.
        try:
            file_name, limit = arguments
        except ValueError:
            pass

        song_name, extension = os.path.splitext(os.path.basename(file_name))

        fingerprints, file_hash = get_file_fingerprints(file_name, limit, print_output=True)

        return song_name, fingerprints, file_hash


def recognize(data, db: 'MySQLDatabase') -> Tuple[List[Dict[str, any]], int, int, int]:
        fingerprint_times = []
        hashes = set()
        fingerprints, fingerprint_time = generate_fingerprints(*data, Fs=16000)
        fingerprint_times.append(fingerprint_time)
        hashes |= set(fingerprints)

        matches, dedup_hashes, query_time = find_matches(hashes, db)

        t = time()
        final_results = align_matches(matches, dedup_hashes, len(hashes), db, TOPN)
        align_time = time() - t

        return final_results, np.sum(fingerprint_times), query_time, align_time

def fingerprint_directory(db: 'MySQLDatabase', path: str, extensions: str, nprocesses: int = None) -> None:
    songs = db.get_songs()
    songhashes_set = set()
    for song in songs:
        song_hash = song[FIELD_FILE_SHA1]
        songhashes_set.add(song_hash)
    limit = 60
    
    try:
        nprocesses = nprocesses or multiprocessing.cpu_count()
    except NotImplementedError:
        nprocesses = 1
    else:
        nprocesses = 1 if nprocesses <= 0 else nprocesses

    pool = multiprocessing.Pool(nprocesses)

    filenames_to_fingerprint = []
    for filename, _ in helpers.find_files(path, extensions):
        # don't refingerprint already fingerprinted files
        if helpers.unique_hash(filename) in songhashes_set:
            print(f"{filename} already fingerprinted, continuing...")
            continue

        filenames_to_fingerprint.append(filename)

    # Prepare _fingerprint_worker input
    worker_input = list(zip(filenames_to_fingerprint, [limit] * len(filenames_to_fingerprint)))

    # Send off our tasks
    iterator = pool.imap_unordered(_fingerprint_worker, worker_input)

    # Loop till we have all of them
    while True:
        try:
            song_name, hashes, file_hash = next(iterator)
        except multiprocessing.TimeoutError:
            continue
        except StopIteration:
            break
        except Exception:
            print("Failed fingerprinting")
            # Print traceback because we can't reraise it here
            traceback.print_exc(file=sys.stdout)
        else:
            sid = db.insert_song(song_name, file_hash, len(hashes))

            db.insert_hashes(sid, hashes)
            db.set_song_fingerprinted(sid)
            songs = db.get_songs()
            songhashes_set = set()  # to know which ones we've computed before
            for song in songs:
                song_hash = song[FIELD_FILE_SHA1]
                songhashes_set.add(song_hash)

    pool.close()
    pool.join()
        

def fingerprint_file(db: 'MySQLDatabase', file_path: str, song_name: str = None) -> None:
    
    songs = db.get_songs()
    songhashes_set = set()
    for song in songs:
        song_hash = song[FIELD_FILE_SHA1]
        songhashes_set.add(song_hash)
    limit = 60
    
    song_name_from_path = os.path.splitext(os.path.basename(file_path))[0]
    song_hash = helpers.unique_hash(file_path)
    song_name = song_name or song_name_from_path
    # don't refingerprint already fingerprinted files
    if song_hash in songhashes_set:
        print(f"{song_name} already fingerprinted, continuing...")
    else:
        song_name, hashes, file_hash = _fingerprint_worker(
            [file_path,
            limit]
        )
        sid = db.insert_song(song_name, file_hash, len(file_hash))

        db.insert_hashes(sid, hashes)
        db.set_song_fingerprinted(sid)
        # get songs previously indexed
        songs = db.get_songs()
        songhashes_set = set()  # to know which ones we've computed before
        for song in songs:
            song_hash = song[FIELD_FILE_SHA1]
            songhashes_set.add(song_hash)