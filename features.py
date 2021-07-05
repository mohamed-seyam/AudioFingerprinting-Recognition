import numpy as np
import scipy.signal

class SpectralFeatures():
    def __init__(self, audio_mix: np.array, sampling_rate: int) -> np.ndarray:
        return self.generate_spectrogram_hash(audio_mix, sampling_rate, 'hann')
        # self.generate_mel_spectrogram_hash(audio_mix, sampling_rate), \
        # self.generate_mfcc_hash(audio_mix, sampling_rate)

    def generate_spectrogram_hash(self, audio_mix: np.array, sampling_rate: int=16000, window_type: str='hann') -> np.ndarray:
        _, _, colorMesh = scipy.signal.spectrogram(audio_mix, fs=sampling_rate, window=window_type)
        print(colorMesh)
        return colorMesh
    
    def generate_mel_spectrogram_hash(self):
        pass

    def generate_mfcc_hash(self):
        pass