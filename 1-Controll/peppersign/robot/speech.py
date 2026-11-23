# -*- coding: utf-8 -*-
"""Voce di Pepper: TTS, parlato animato, volume e registrazione audio (SAY_AND_LISTEN)."""
from __future__ import absolute_import

from peppersign.audio import get_wav_bytes_from_pepper, record_wav_on_pepper
from peppersign.http_utils import webapp_upload_audio
from peppersign.utils import clamp, safe_unicode


class Speech(object):
    def __init__(self, robot):
        self.robot = robot
        self.cached_volume = None

    # ------------------------------------------------------------ parlato
    def _to_speech_payload(self, text_u):
        try:
            return text_u.encode("utf-8")
        except (UnicodeError, AttributeError):
            return str(text_u)

    def apply_speaking_movement_defaults_locked(self):
        robot = self.robot
        if not robot.speaking_movement:
            return
        defaults = robot.config.get("robot_defaults", {})
        if not defaults.get("animated_say_use_speaking_movement", True):
            return
        mode = safe_unicode(defaults.get("animated_say_mode", "contextual")).strip().lower() or "contextual"
        try:
            robot.speaking_movement.setMode(mode)
        except Exception as exc:
            robot.log("[WARN] ALSpeakingMovement.setMode(%s) fallita: %s" % (mode, str(exc)))

    def _say_plain_locked(self, text_u):
        robot = self.robot
        payload = self._to_speech_payload(text_u)
        try:
            robot.tts.say(payload)
            return True
        except Exception:
            try:
                robot.tts.say(str(text_u))
                return True
            except Exception as exc:
                robot.set_error("TTS fallito: %s" % str(exc))
                return False

    def say(self, text):
        """Ritorna (ok, messaggio)."""
        text_u = safe_unicode(text).strip()
        if not text_u:
            return False, "testo vuoto"
        with self.robot.lock:
            if self._say_plain_locked(text_u):
                return True, "detto"
            return False, self.robot.last_error or "TTS fallito"

    def say_animated(self, text):
        robot = self.robot
        text_u = safe_unicode(text).strip()
        if not text_u:
            return False, "testo vuoto"

        with robot.lock:
            self.apply_speaking_movement_defaults_locked()

            if robot.animated_speech:
                try:
                    robot.animated_speech.say(self._to_speech_payload(text_u))
                    return True, "animated speech ok"
                except Exception as exc:
                    fallback = robot.config["robot_defaults"].get("animated_say_fallback_to_tts", True)
                    if not fallback:
                        robot.set_error("Animated speech fallita: %s" % str(exc))
                        return False, "animated speech fallita: %s" % str(exc)

                    robot.log("[WARN] AnimatedSpeech fallita, fallback su TTS: %s" % str(exc))
                    if self._say_plain_locked(text_u):
                        return True, "fallback su TTS classico"
                    return False, "animated speech fallita e fallback TTS non riuscito"

            if self._say_plain_locked(text_u):
                return True, "ALAnimatedSpeech non disponibile: usato TTS classico"
            return False, "ALAnimatedSpeech non disponibile e TTS fallito"

    # ------------------------------------------------------------ volume
    def _get_volume_locked(self):
        value = self.robot.audio_device.getOutputVolume()
        try:
            value = int(round(float(value)))
        except (TypeError, ValueError, OverflowError):
            value = int(value)
        value = int(clamp(value, 0, 100))
        self.cached_volume = value
        return value

    def _set_volume_locked(self, value):
        volume = int(round(float(value)))
        volume = int(clamp(volume, 0, 100))
        self.robot.audio_device.setOutputVolume(volume)
        self.cached_volume = volume
        return volume

    def _resolve_volume_step(self, step):
        if step is None:
            step = self.robot.config.get("robot_defaults", {}).get("volume_step", 10)
        try:
            step = int(round(float(step)))
        except (TypeError, ValueError, OverflowError):
            step = 10
        if step < 1:
            step = 1
        if step > 100:
            step = 100
        return step

    def get_volume(self):
        if not self.robot.audio_device:
            return False, "ALAudioDevice non disponibile"
        with self.robot.lock:
            try:
                return True, self._get_volume_locked()
            except Exception as exc:
                return False, "Errore getOutputVolume: %s" % str(exc)

    def set_volume(self, value):
        if not self.robot.audio_device:
            return False, "ALAudioDevice non disponibile"
        with self.robot.lock:
            try:
                volume = self._set_volume_locked(value)
                return True, "Volume impostato a %d%%" % volume
            except Exception as exc:
                return False, "Errore setOutputVolume: %s" % str(exc)

    def volume_up(self, step=None):
        if not self.robot.audio_device:
            return False, "ALAudioDevice non disponibile"
        delta = self._resolve_volume_step(step)
        with self.robot.lock:
            try:
                current = self._get_volume_locked()
                target = self._set_volume_locked(current + delta)
                return True, "Volume aumentato a %d%%" % target
            except Exception as exc:
                return False, "Errore aumento volume: %s" % str(exc)

    def volume_down(self, step=None):
        if not self.robot.audio_device:
            return False, "ALAudioDevice non disponibile"
        delta = self._resolve_volume_step(step)
        with self.robot.lock:
            try:
                current = self._get_volume_locked()
                target = self._set_volume_locked(current - delta)
                return True, "Volume abbassato a %d%%" % target
            except Exception as exc:
                return False, "Errore riduzione volume: %s" % str(exc)

    def refresh_volume_cache(self):
        """Volume letto solo se il robot non sta eseguendo un altro comando (nessuna attesa sul lock)."""
        if not self.robot.audio_device:
            return
        lock = self.robot.lock
        generation = self.robot.generation
        if lock.acquire(False):
            try:
                if self.robot.generation == generation:
                    self._get_volume_locked()
            except Exception as exc:
                self.robot.report("volume", "[AUDIO] Volume non leggibile: %s" % exc)
            finally:
                lock.release()

    # ------------------------------------------------------------ registrazione audio
    def say_and_listen(self, session_id, prompt):
        robot = self.robot
        config = robot.config
        sid = safe_unicode(session_id).strip()
        if not sid:
            return False, "sessionId mancante"

        prompt_u = safe_unicode(prompt).strip() or u"Ciao! Dimmi la parola."
        self.say(prompt_u)

        with robot.lock:
            try:
                robot.log(">>> Registrazione in corso (%d sec)..." % config["audio"]["rec_seconds"])
                record_wav_on_pepper(
                    robot.recorder,
                    config["audio"]["remote_wav"],
                    config["audio"]["rec_seconds"],
                )
            except Exception as exc:
                return False, "errore registrazione: %s" % str(exc)

            try:
                wav_bytes = get_wav_bytes_from_pepper(
                    robot.fileman,
                    config["audio"]["remote_wav"],
                    robot.tts,
                )
            except Exception as exc:
                robot.log("[AUDIO] Lettura della registrazione dal robot non riuscita: %s" % exc)
                wav_bytes = None

        if (not wav_bytes) or (len(wav_bytes) <= 44):
            self.say("Ho registrato ma l'audio sembra vuoto.")
            return False, "audio vuoto"

        try:
            code, body = webapp_upload_audio(
                config["webapp"]["audio_upload_url"],
                sid,
                wav_bytes,
                timeout=config["webapp"]["audio_upload_timeout"],
            )
            if code == 200:
                self.say("Audio inviato.")
                return True, "upload ok"
            self.say("Errore durante l'invio dell'audio.")
            return False, "upload status %s, body: %s" % (code, body[:200])
        except Exception as exc:
            self.say("Errore durante l'invio.")
            return False, "upload exc: %s" % str(exc)
