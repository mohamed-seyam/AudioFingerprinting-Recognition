from helpers import get_data
from typing import List
import PyQt5.QtWidgets as qtw
import PyQt5.QtCore as qtc
import sys
import os
import numpy as np
from ui_Main import Ui_MainWindow
from ui_Output import Ui_matches
from helpers import get_data
import recognizer
from database_handler.mysql_database import MySQLDatabase
from time import time
import json
from operator import itemgetter
import argparse
from argparse import RawTextHelpFormatter
from configuration import (TOTAL_TIME, FINGERPRINT_TIME, QUERY_TIME, ALIGN_TIME, RESULTS, DEFAULT_CONFIG_FILE)


def initDatabase(configpath):
    """
    Load config from a JSON file
    """
    try:
        with open(configpath) as f:
            config = json.load(f)
    except IOError as err:
        print(f"Cannot open configuration: {str(err)}. Exiting")
        sys.exit(1)

    return MySQLDatabase(**config.get("database", {}))

class MatchesWindow(qtw.QWidget):
    def __init__(self, results):
        super().__init__()
        self.ui = Ui_matches()
        self.ui.setupUi(self)
        self.show()

        self.ui.back.clicked.connect(self.back)
        # pprint(results)
        _translate = qtc.QCoreApplication.translate
        results = sorted(results['results'], key=itemgetter('input_confidence'), reverse=True)
        song = results[0]['song_name'].decode('utf-8').split('-')
        song_name = song[1].strip()
        artist = song[0].strip()
        self.ui.song_info.setText(_translate("matches", f"<html><head/><body><p align=\"center\"><span style=\" font-size:10pt; font-weight:600;\">{song_name}</span></p><p align=\"center\"><span style=\" font-weight:600;\">by: {artist}</span></p></body></html>"))
        
        for row in range(10):
            self.ui.song_matches.setItem(row, 0, qtw.QTableWidgetItem(results[row]['song_name'].decode('utf-8')))
            self.ui.song_matches.setItem(row, 1, qtw.QTableWidgetItem(str(round(results[row]['input_confidence'] * 100))+"%"))

        self.ui.song_matches.resizeColumnsToContents()


    def back(self):
        self.close()
        self.mainWindow = MainWindow()

class MainWindow(qtw.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.show()

        self.SAMPLING_RATE = 16000
        self.audio_files = []
        self.mixed_audio = np.ndarray([])
        configPath = DEFAULT_CONFIG_FILE
        self.db = initDatabase(configPath)

        self.ui.load_songs.clicked.connect(self.load)
        self.ui.shazam.clicked.connect(self.generate)

        self.ui.actionExit.triggered.connect(self.close)
        self.ui.actionNew.triggered.connect(self.new_instance)

        self.ui.song_1_percentage.valueChanged.connect(lambda value: self.mix(value))

    def new_instance(self):
        self.new_window = MainWindow()
        self.new_window.show

    def load(self):
        filter = "MUSIC (*.mp3)"
        caption = 'Open File'
        pwd = os.getcwd()
        options = qtw.QFileDialog.Options()
        options |= qtw.QFileDialog.DontUseNativeDialog

        files_names = qtw.QFileDialog.getOpenFileNames(None, caption=caption, directory=pwd, filter=filter,options=options)[0]
        if(not files_names):
            return
        for i in range(min(2, len(files_names))):
            data, _, _ = get_data(files_names[i])
            self.audio_files.append(data)
        return self.mix(100)

    def mix(self, ratio: float) -> np.ndarray:
        if(len(self.audio_files) == 1):
            self.mixed_audio = self.audio_files[0]
        else:
            self.ui.song_1_percentage.setDisabled(False)
            self.mixed_audio = np.multiply(self.audio_files[0], ratio/100) + np.multiply(self.audio_files[1], (1 - ratio/100))

        self.ui.shazam.setDisabled(False)
        

    def generate(self) -> None:
        t = time()
        matches, fingerprint_time, query_time, align_time = recognizer.recognize(self.mixed_audio, self.db)
        t = time() - t

        results = {
            TOTAL_TIME: t,
            FINGERPRINT_TIME: fingerprint_time,
            QUERY_TIME: query_time,
            ALIGN_TIME: align_time,
            RESULTS: matches
        }

        self.close()
        self.matches = MatchesWindow(results)
        


def main_window() -> None:
    app = qtw.QApplication(sys.argv)
    app.setStyle("Fusion")
    main_window = MainWindow()
    sys.exit(app.exec_())

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Dejavu: Audio Fingerprinting library",
        formatter_class=RawTextHelpFormatter)
    parser.add_argument('-c', '--config', nargs='?',
                        help='Path to configuration file\n'
                             'Usages: \n'
                             '--config /path/to/config-file\n')
    parser.add_argument('-f', '--fingerprint', nargs='*',
                        help='Fingerprint files in a directory\n'
                             'Usages: \n'
                             '--fingerprint /path/to/directory extension\n'
                             '--fingerprint /path/to/directory')
    args = parser.parse_args()

    if not(args.fingerprint or args.config):
        main_window()
    else:
        config_file = args.config
        if config_file is None:
            config_file = DEFAULT_CONFIG_FILE
        db = initDatabase(config_file)
        if args.fingerprint:
        # Fingerprint all files in a directory
            if len(args.fingerprint) == 2:
                directory = args.fingerprint[0]
                extension = args.fingerprint[1]
                print(f"Fingerprinting all .{extension} files in the {directory} directory")
                recognizer.fingerprint_directory(db, directory, ["." + extension], 4)

            elif len(args.fingerprint) == 1:
                filepath = args.fingerprint[0]
                if os.path.isdir(filepath):
                    print("Please specify an extension if you'd like to fingerprint a directory!")
                    sys.exit(1)
                recognizer.fingerprint_file(db=db, file_path=filepath)