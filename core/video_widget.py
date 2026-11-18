#  video_widget.py Copyright (c) 2026 Nikki Cooper
#
#  This program and the accompanying materials are made available under the
#  terms of the GNU Lesser General Public License, version 3.0 which is available at
#  https://www.gnu.org/licenses/gpl-3.0.html#license-text
#
"""
Video Widget - Qt native video playback
Hardware-accelerated video playback using QtMultimedia
"""

from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink, QVideoFrame
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt, Signal

SCREENSHOT_WIDTH  = 3840
SCREENSHOT_HEIGHT = 2160


class VideoWidget(QVideoWidget):
    """
    Qt native video widget with hardware acceleration.
    Uses QtMultimedia for proper Wayland support and VA-API acceleration.

    Frame pipeline (greyscale filter):
        QMediaPlayer → _process_sink (QVideoSink)
                           ↓  videoFrameChanged
                       _on_frame_received()
                           ↓  optionally zero NV12 UV plane
                       videoSink().setVideoFrame()   ← display
    """

    # Signal emitted when video ends
    video_ended = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Set aspect ratio mode
        self.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)

        # Audio output and frame sink outlive the media player (see _new_player()), so
        # volume / mute and the greyscale/screenshot frame path survive a player swap.
        self.audio_output = QAudioOutput()

        # Greyscale filter: player feeds _process_sink; we optionally modify
        # the NV12 UV (chroma) plane before pushing to the display sink.
        self._process_sink = QVideoSink(self)
        self._process_sink.videoFrameChanged.connect(self._on_frame_received)
        self._grayscale = False

        # Create media player (wired to audio_output, _process_sink, status handler)
        self.player = None
        self._new_player()

        # Default playback rate
        self._speed = 2.0

        # Playback-rate handling (Qt GStreamer backend). A rate change is a seek, and it is
        # only safe on a pipeline that is actively playing the CURRENT source:
        #   - On a pipeline at EndOfMedia (GStreamer stays in PlayingState there) it re-emits
        #     a stale BufferedMedia + EndOfMedia that land on the next source and end it.
        #   - On a stopped/ended/loading pipeline it is deferred and later executed as a seek
        #     to the OLD position, so the next video starts part-way through (or ends at once
        #     if it is shorter than the previous one).
        #   - When a new source starts, the backend resets the rate to 1.0 without emitting
        #     playbackRateChanged.
        # So: set_speed() only stores the speed unless the current source is in
        # BufferedMedia (see _can_set_rate()), and the stored speed is applied every time
        # the current source reaches BufferedMedia.
        self._rate_ready = False     # current source has reached BufferedMedia at least once
        self._url = None

        # Loop state
        self.is_looping = False

        # Latest decoded frame (original, pre-greyscale) for screenshot capture
        self._last_frame = None

    # ── Frame pipeline ──────────────────────────────────────────────────────

    def _on_frame_received(self, frame):
        """Receive decoded frame, optionally apply greyscale, push to display."""
        self._last_frame = frame            # store original for screenshots
        if self._grayscale:
            frame = self._apply_grayscale(frame)
        self.videoSink().setVideoFrame(frame)

    def _apply_grayscale(self, frame: QVideoFrame) -> QVideoFrame:
        """
        Return a greyscale copy of the frame.

        PySide6's QVideoFrame.bits() returns a bytes copy — not a writable
        pointer — so direct NV12 UV-plane manipulation isn't available from
        Python.  Instead: convert to QImage, strip chroma via Format_Grayscale8,
        wrap back as QVideoFrame.  Cost: one YUV→ARGB + one ARGB→Gray
        conversion (~2 ms at 1080p); negligible for an on-demand toggle.
        Falls back to the original frame if any conversion step fails.
        """
        img = frame.toImage()
        if img.isNull():
            return frame
        gray = img.convertedTo(QImage.Format.Format_Grayscale8)
        if gray.isNull():
            return frame
        result = QVideoFrame(gray)
        return result if result.isValid() else frame

    def set_grayscale(self, enabled: bool):
        """Enable or disable the greyscale filter."""
        self._grayscale = enabled

    # ── Screenshot ──────────────────────────────────────────────────────────

    def capture_frame(self):
        """
        Return the most recently decoded video frame as a QImage at native
        resolution, or None if no frame is available yet.
        Always returns the original (pre-greyscale) frame.
        The caller is responsible for scaling / saving.
        """
        if self._last_frame is None or not self._last_frame.isValid():
            return None
        img = self._last_frame.toImage()
        return img if not img.isNull() else None

    def _new_player(self):
        """
        Create a fresh QMediaPlayer, replacing the current one.

        Qt's GStreamer backend reuses its decoding pipeline across setSource() calls, and
        that pipeline keeps the decoder list it was built with. GStreamer decoder rank
        changes made later (HWAccel.prepare_for_file()) only reach a NEW player. So
        load_file(new_player=True) is used when the eligible decoder set changes.
        Callers must access self.player at call time, not keep a reference to it.
        """
        old = self.player
        if old is not None:
            old.mediaStatusChanged.disconnect(self._on_media_status_changed)
            old.stop()
            old.setAudioOutput(None)
            old.setVideoOutput(None)
            old.deleteLater()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self._process_sink)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

    # ── Media status ────────────────────────────────────────────────────────

    def _on_media_status_changed(self, status):
        """Handle media status changes"""
        if status == QMediaPlayer.MediaStatus.BufferedMedia:
            # Current source is playing with a valid position: rate changes are safe now.
            # Apply the stored speed (see the note in __init__).
            if self.player.source() == self._url:
                self._rate_ready = True
                self._sync_rate()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.is_looping:
                # Restart video from beginning; the rate is re-applied on BufferedMedia
                self.player.setPosition(0)
                self.player.play()
            else:
                self.video_ended.emit()

    # ── Playback controls ───────────────────────────────────────────────────

    def load_file(self, filepath, new_player=False):
        """
        Load and play a video file.
        new_player=True swaps in a fresh QMediaPlayer first, so GStreamer decoder rank
        changes made since the current player was built take effect (see _new_player()).
        """
        from PySide6.QtCore import QUrl
        if new_player:
            self._new_player()
        # No setPlaybackRate() here: the speed is applied once the new source reaches
        # BufferedMedia (see the note in __init__).
        self._rate_ready = False
        self._url = QUrl.fromLocalFile(filepath)
        self.player.setSource(self._url)
        self.player.play()

    def play(self):
        """Resume playback"""
        self.player.play()

    def pause(self):
        """Pause playback"""
        self.player.pause()

    def toggle_pause(self):
        """Toggle play/pause"""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def stop(self):
        """Stop playback"""
        self.player.stop()

    def set_speed(self, speed):
        """Set playback speed (e.g., 2.0 for 2x)"""
        self._speed = speed
        # Between videos (ended, loading) only store it; it is applied on BufferedMedia.
        # This is the --autoSpeed path: tag/restore speeds are set before load_file().
        if self._can_set_rate():
            self.player.setPlaybackRate(speed)

    def _can_set_rate(self):
        """True when a rate change is safe: the current source is playing, buffered."""
        return (self._rate_ready
                and self.player.mediaStatus() == QMediaPlayer.MediaStatus.BufferedMedia
                and self.player.source() == self._url)

    def _sync_rate(self):
        """Apply self._speed to the player if its current rate differs."""
        if self.player.playbackRate() != self._speed:
            self.player.setPlaybackRate(self._speed)

    def seek(self, milliseconds):
        """
        Seek by a relative amount (positive for forward, negative for backward).

        Args:
            milliseconds: Amount to seek in milliseconds (can be negative)

        Returns:
            tuple: (current_position_ms, duration_ms) or (None, None) if seeking failed
        """
        current_pos = self.player.position()
        duration = self.player.duration()

        if duration <= 0:
            return None, None

        # Calculate new position
        new_pos = current_pos + milliseconds

        # Clamp to valid range
        new_pos = max(0, min(new_pos, duration))

        # Perform the seek
        self.player.setPosition(new_pos)

        return new_pos, duration

    def get_position_info(self):
        """
        Get current playback position information.

        Returns:
            tuple: (current_position_ms, duration_ms, percentage)
        """
        current_pos = self.player.position()
        duration = self.player.duration()

        if duration > 0:
            percentage = (current_pos / duration) * 100
        else:
            percentage = 0

        return current_pos, duration, percentage

    @property
    def is_playing(self):
        """Check if currently playing"""
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def toggle_loop(self):
        """Toggle video looping on/off"""
        self.is_looping = not self.is_looping
        return self.is_looping

    def restart(self):
        """Seek to beginning and ensure playback is running."""
        self.player.setPosition(0)
        self.player.play()

    def close_player(self):
        """Clean up player"""
        self.player.stop()
