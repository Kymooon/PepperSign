# -*- coding: utf-8 -*-
from __future__ import absolute_import

import time


def record_wav_on_pepper(recorder_service, remote_wav, rec_seconds):
    try:
        recorder_service.stopMicrophonesRecording()
    except Exception:
        pass

    recorder_service.startMicrophonesRecording(remote_wav, "wav", 16000, (0, 0, 1, 0))
    time.sleep(rec_seconds)
    recorder_service.stopMicrophonesRecording()
    time.sleep(0.3)


def get_wav_bytes_from_pepper(file_manager, remote_wav, tts=None):
    if not file_manager.fileExists(remote_wav):
        if tts:
            try:
                tts.say("Non riesco a salvare l'audio sul robot.")
            except Exception:
                pass
        return None

    wav_data = file_manager.getFileContents(remote_wav)
    if isinstance(wav_data, list):
        return "".join([chr(x & 0xFF) for x in wav_data])
    return wav_data
