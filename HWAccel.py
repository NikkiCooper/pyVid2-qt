#  HWAccel.py Copyright (c) 2026 Nikki Cooper
#
#  This program and the accompanying materials are made available under the
#  terms of the GNU Lesser General Public License, version 3.0 which is available at
#  https://www.gnu.org/licenses/gpl-3.0.html#license-text
#
"""
HWAccel.py — Hardware decoder detection and GStreamer rank configuration.

Call setup_decoder() BEFORE QApplication so that rank changes and any env-var
settings are in place before Qt's multimedia stack constructs its pipeline.

Rank changes only take effect when Qt Multimedia runs on its GStreamer backend
(QT_MEDIA_BACKEND=gstreamer, set in main.py). Qt's default FFmpeg backend makes its
own hardware choice (CUDA first) and ignores GStreamer ranks entirely.

Decoder categories:
    nvdec     NVIDIA NVDEC (nvcodec plugin: nvh265dec, nvh264dec, nvav1dec, ...)
    vaapi     VA-API (va plugin: vah265dec, ...; legacy gstreamer-vaapi: vaapih265dec, ...)
    software  everything else (avdec_*, libde265dec, dav1ddec, ...)

Vulkan video decoders are deliberately unsupported. GStreamer registers them at
rank NONE (not ready for autoplugging); pyVid2-qt keeps them at NONE.
"""

import os
from Bcolors import Bcolors

bc = Bcolors()

# Display probe list for the startup banner: (element_name, display_label, category).
# First match per category is shown. HEVC first — it is the primary content format.
_DISPLAY_CANDIDATES = [
    ('nvh265dec',    'NVDEC',    'nvdec'),
    ('nvh264dec',    'NVDEC',    'nvdec'),
    ('vah265dec',    'VA-API',   'vaapi'),
    ('vah264dec',    'VA-API',   'vaapi'),
    ('vaapih265dec', 'VA-API',   'vaapi'),
    ('vaapih264dec', 'VA-API',   'vaapi'),
    ('avdec_h265',   'FFmpeg',   'software'),   # rank PRIMARY — preferred over libde265
    ('avdec_h264',   'FFmpeg',   'software'),
    ('libde265dec',  'libde265', 'software'),   # rank SECONDARY
]

# Hardware categories shown in the "not available" section if absent
_HW_ORDER = ['nvdec', 'vaapi']

_PCI_VENDOR_INTEL = '0x8086'


# ── GStreamer helpers ──────────────────────────────────────────────────────────

def _init_gst():
    """Return (Gst, True) or (None, False) if GStreamer Python bindings are absent."""
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        Gst.init(None)
        return Gst, True
    except Exception:
        return None, False


def _category(factory):
    """
    Classify a video decoder factory as 'nvdec', 'vaapi', 'vulkan' or 'software'.

    VA-API elements whose device is NVIDIA (libva-nvidia-driver) are classed as
    'nvdec': they run on the NVIDIA GPU, so --decoder vaapi must exclude them.
    """
    name = factory.get_name()
    if name.startswith('vulkan'):
        return 'vulkan'
    if name.startswith('nv'):
        return 'nvdec'
    if name.startswith('va'):
        if 'nvidia' in (factory.get_metadata('long-name') or '').lower():
            return 'nvdec'
        return 'vaapi'
    return 'software'


def _video_decoders(Gst):
    """Return {category: [factory, ...]} for every registered video decoder."""
    cats = {'nvdec': [], 'vaapi': [], 'vulkan': [], 'software': []}
    for f in Gst.Registry.get().get_feature_list(Gst.ElementFactory):
        klass = f.get_metadata('klass') or ''
        if 'Decoder' in klass and 'Video' in klass:
            cats[_category(f)].append(f)
    return cats


def _probe(Gst):
    """
    Return list of (elem_name, label, category, rank) for the startup banner.
    Only the first available match per category is included.
    """
    results = []
    seen = set()
    for elem_name, label, category in _DISPLAY_CANDIDATES:
        if category in seen:
            continue
        factory = Gst.ElementFactory.find(elem_name)
        if factory:
            results.append((elem_name, label, category, factory.get_rank()))
            seen.add(category)
    return results


def _demote(Gst, decoders, *categories):
    """Set GStreamer rank to NONE for every decoder in the named categories."""
    for cat in categories:
        for factory in decoders[cat]:
            factory.set_rank(Gst.Rank.NONE)


def _promote(Gst, decoders, category):
    """
    Raise every decoder in `category` above all software decoders.
    Elements upstream registered at rank NONE (e.g. vajpegdec) are left disabled.
    """
    floor = Gst.Rank.PRIMARY + 10
    for factory in decoders[category]:
        rank = factory.get_rank()
        if rank > Gst.Rank.NONE and rank < floor:
            factory.set_rank(floor)


def _intel_gpu_present():
    """True if any DRM render node belongs to an Intel GPU."""
    base = '/sys/class/drm'
    try:
        nodes = [n for n in os.listdir(base) if n.startswith('renderD')]
    except OSError:
        return False
    for node in nodes:
        try:
            with open(os.path.join(base, node, 'device', 'vendor')) as fh:
                if fh.read().strip() == _PCI_VENDOR_INTEL:
                    return True
        except OSError:
            continue
    return False


# ── Public API ─────────────────────────────────────────────────────────────────

def _configure(pref):
    """
    Configure GStreamer decoder ranks based on the --decoder preference.

        auto      upstream GStreamer ranks are left untouched
        nvdec     only NVDEC hardware decoders are eligible (plus software fallback)
        vaapi     only VA-API decoders on non-NVIDIA GPUs are eligible (plus software
                  fallback); the NVIDIA GPU is not used for decoding at all
        software  all hardware decoders are disabled

    Returns:
        (active_label, probe_results)
        active_label  — display name of the decoder that will be used
        probe_results — list of (elem_name, label, category, rank)
    """
    Gst, ok = _init_gst()
    if not ok:
        return 'Unknown (GStreamer bindings unavailable)', []

    available = _probe(Gst)
    if not available:
        return 'None found', []

    decoders = _video_decoders(Gst)

    # category → (elem_name, label, rank)
    by_cat = {cat: (elem, label, rank) for elem, label, cat, rank in available}

    if pref == 'auto':
        # Let GStreamer decide — highest registered rank wins
        best = max(available, key=lambda x: x[3])
        return best[1], available

    # Every explicit choice keeps Vulkan decoders out of autoplugging.
    _demote(Gst, decoders, 'vulkan')

    if pref == 'nvdec':
        if 'nvdec' in by_cat:
            _demote(Gst, decoders, 'vaapi')
            _promote(Gst, decoders, 'nvdec')
            return by_cat['nvdec'][1], available
        print(f"{bc.Yellow_f}--decoder nvdec: NVDEC not available — falling back to auto{bc.RESET}")
        return _configure('auto')

    elif pref == 'vaapi':
        if 'vaapi' in by_cat:
            # With libva-nvidia-driver installed, libva could otherwise pick the
            # NVIDIA driver. Only force Intel's iHD driver when an Intel GPU exists,
            # so AMD (Mesa radeonsi) systems are unaffected.
            if not os.environ.get('LIBVA_DRIVER_NAME') and _intel_gpu_present():
                os.environ['LIBVA_DRIVER_NAME'] = 'iHD'
            _demote(Gst, decoders, 'nvdec')
            _promote(Gst, decoders, 'vaapi')
            return by_cat['vaapi'][1], available
        print(f"{bc.Yellow_f}--decoder vaapi: VA-API not available — falling back to auto{bc.RESET}")
        return _configure('auto')

    elif pref == 'software':
        _demote(Gst, decoders, 'nvdec', 'vaapi')
        sw = next((r for r in available if r[2] == 'software'), None)
        return (sw[1] if sw else 'Software'), available

    return 'Unknown', available


def setup_decoder(pref='auto', rgb_fallback='software'):
    """
    Configure GStreamer decoder ranks based on the --decoder preference.
    See _configure() for the meaning of each preference.

    rgb_fallback ('software' | 'nvdec', --rgbFallback): decoder for RGB-coded files when
    VA-API has to sit out (see prepare_for_file()). Only matters with --decoder vaapi, where
    NVDEC is otherwise disabled: 'nvdec' re-enables NVDEC for those files only.

    Returns:
        (active_label, probe_results)
        active_label  — display name of the decoder that will be used
        probe_results — list of (elem_name, label, category, rank)
    """
    Gst, ok = _init_gst()
    nv_orig = ([(f, f.get_rank()) for f in _video_decoders(Gst)['nvdec']] if ok else [])
    result = _configure(pref)
    _remember_eligible_va()
    _va_state['pref'] = pref
    _va_state['nv_ranks'] = []
    if ok and rgb_fallback == 'nvdec' and pref == 'vaapi' and _va_state['ranks']:
        # NVDEC decoders that --decoder vaapi disabled; re-enabled for RGB-coded files only
        _va_state['nv_ranks'] = [(f, r) for f, r in nv_orig
                                 if r > Gst.Rank.NONE and f.get_rank() == Gst.Rank.NONE]
        if not _va_state['nv_ranks']:
            print(f"{bc.Yellow_f}--rgbFallback nvdec: NVDEC not available — RGB-coded files "
                  f"will be decoded in software{bc.RESET}")
    elif rgb_fallback == 'nvdec' and pref != 'vaapi':
        print(f"{bc.Yellow_f}--rgbFallback nvdec has no effect without --decoder vaapi{bc.RESET}")
    return result


# ── Per-file VA-API exclusion (RGB-coded video) ───────────────────────────────
#
# GStreamer's VA decoders output RGB-coded streams (e.g. HEVC Rext 'gbrp', colour matrix
# GBR/identity) as a YUV 4:4:4 format (VUYA / Y410) while the caps still carry the RGB
# matrix. Downstream converts it as YUV, so colours come out wrong: saturated colours are
# blown out, neutrals look fine. avdec_* and nvh265dec output proper GBR and are correct.
# Ordinary YUV 4:2:0 / 4:4:4 streams are unaffected. For RGB-coded files only, VA decoders
# are taken out of autoplugging; the next eligible decoder is used for that file (software
# under --decoder vaapi, since NVDEC is already excluded there, so the NVIDIA GPU stays idle).

_va_state = {
    'gst': None,
    'ranks': [],        # (factory, configured rank) of VA decoders eligible after setup
    'nv_ranks': [],     # (factory, original rank) of NVDEC decoders to enable for RGB files
                        # (--decoder vaapi --rgbFallback nvdec only)
    'pref': 'auto',
    'excluded': False,  # True while the per-file RGB override is applied
    'discoverer': None,
}


def _remember_eligible_va():
    """Record VA decoders that are eligible (rank > NONE) after configuration."""
    Gst, ok = _init_gst()
    if not ok:
        return
    _va_state['gst'] = Gst
    _va_state['ranks'] = [(f, f.get_rank()) for f in _video_decoders(Gst)['vaapi']
                          if f.get_rank() > Gst.Rank.NONE]
    _va_state['excluded'] = False


def _is_rgb_coded(path):
    """True if any video stream in `path` uses the RGB (identity / GBR) colour matrix."""
    Gst = _va_state['gst']
    try:
        import gi
        gi.require_version('GstPbutils', '1.0')
        gi.require_version('GstVideo', '1.0')
        from gi.repository import GstPbutils, GstVideo
        if _va_state['discoverer'] is None:
            _va_state['discoverer'] = GstPbutils.Discoverer.new(2 * Gst.SECOND)
        info = _va_state['discoverer'].discover_uri(Gst.filename_to_uri(os.path.abspath(path)))
    except Exception:
        return False
    for stream in info.get_video_streams():
        caps = stream.get_caps()
        if not caps or caps.get_size() == 0:
            continue
        col = caps.get_structure(0).get_value('colorimetry')
        if not col:
            continue
        cinfo = GstVideo.VideoColorimetry()
        if cinfo.from_string(col) and cinfo.matrix == GstVideo.VideoColorMatrix.RGB:
            return True
    return False


def prepare_for_file(path):
    """
    Call before loading each video. Excludes VA-API decoders for RGB-coded files (which
    VA-API renders with wrong colours) and restores them for everything else.
    No-op when no VA decoder is eligible (--decoder nvdec / software, or no GStreamer).

    Returns (changed, note):
        changed  True if the eligible decoder set CHANGED for this file. The caller must
                 then load the file into a new QMediaPlayer: Qt's GStreamer pipeline keeps
                 the decoder list it was built with, so a rank change does not reach an
                 existing player.
        note     short console tag for RGB-coded files, None otherwise, e.g.
                 "RGB-coded: VA-API skipped (wrong colours) → software"   (--decoder vaapi)
                 "RGB-coded: VA-API skipped (wrong colours) → NVDEC"      (+ --rgbFallback nvdec)
                 No note under --decoder auto when NVDEC takes over: NVDEC would have
                 decoded the file anyway and renders it correctly. VA-API is still excluded
                 then, because NVDEC and VA-API share the same rank and only GStreamer's
                 tie-breaking makes NVDEC win.
    """
    Gst, ranks = _va_state['gst'], _va_state['ranks']
    if Gst is None or not ranks:
        return False, None
    rgb = _is_rgb_coded(path)
    changed = rgb != _va_state['excluded']
    if rgb and not _va_state['excluded']:
        for factory, _ in ranks:
            factory.set_rank(Gst.Rank.NONE)
        for factory, rank in _va_state['nv_ranks']:      # --rgbFallback nvdec
            factory.set_rank(rank)
        _va_state['excluded'] = True
    elif not rgb and _va_state['excluded']:
        for factory, rank in ranks:
            factory.set_rank(rank)
        for factory, _ in _va_state['nv_ranks']:
            factory.set_rank(Gst.Rank.NONE)
        _va_state['excluded'] = False
    note = None
    if rgb:
        fallback = 'NVDEC' if _nvdec_eligible(Gst) else 'software'
        # Under --decoder auto, NVDEC would have decoded the file anyway: nothing to report.
        if not (_va_state['pref'] == 'auto' and fallback == 'NVDEC'):
            note = f"RGB-coded: VA-API skipped (wrong colours) → {fallback}"
    return changed, note


def _nvdec_eligible(Gst):
    """True if NVDEC decoders can be autoplugged (i.e. they take over when VA-API is excluded)."""
    return any(f.get_rank() > Gst.Rank.NONE for f in _video_decoders(Gst)['nvdec'])


def gstreamer_backend_active():
    """
    Return (ok, reason). ok is True when Qt Multimedia will use its GStreamer backend,
    i.e. when the GStreamer rank changes made by setup_decoder() actually affect playback.
    """
    backend = os.environ.get('QT_MEDIA_BACKEND', '')
    if backend != 'gstreamer':
        return False, f"QT_MEDIA_BACKEND={backend or '<unset>'} (Qt default backend is FFmpeg)"
    try:
        from PySide6.QtCore import QLibraryInfo
        plugin_dir = os.path.join(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath), 'multimedia')
    except Exception:
        return False, 'Qt plugin directory could not be determined'
    if os.path.isfile(os.path.join(plugin_dir, 'libgstreamermediaplugin.so')):
        return True, ''
    return False, (f"Qt GStreamer media plugin not found in {plugin_dir} — Qt will fall back to "
                   f"FFmpeg (Arch: install qt6-multimedia-gstreamer and use the system pyside6)")


def warn_if_decoder_ineffective(pref):
    """Print a warning if --decoder cannot take effect on the active Qt backend."""
    ok, reason = gstreamer_backend_active()
    if not ok:
        print(f"{bc.Yellow_f}WARNING: --decoder {pref} has no effect: {reason}{bc.RESET}")
        print(f"{bc.Yellow_f}         Qt will choose the hardware decoder itself (CUDA/NVDEC first).{bc.RESET}\n")


def print_startup_info(version, active_label, available, pref='auto'):
    """Print version banner and decoder status table to stdout."""
    Gst, gst_ok = _init_gst()
    rgb_only = {f.get_name() for f, _ in _va_state['nv_ranks']}
    B, R = bc.BOLD, bc.RESET
    sep = f"{bc.Blue_f}{'─' * 56}{R}"

    print(f"\n{B}{bc.Blue_f}pyVid2-qt{R}  {bc.Light_Yellow_f}version {version}{R}")
    print(sep)

    available_cats = {cat for _, _, cat, _ in available}

    # ── Available decoders ────────────────────────────────────────────────────
    first = True
    for elem_name, label, category, _ in available:
        prefix = 'Decoder:  ' if first else '          '
        first = False

        if label == active_label:
            tag   = f"{B}{bc.Light_Green_f}[active]{R}"
            lbl_s = f"{B}{bc.White_f}{label:<10}{R}"
        elif category == 'software':
            tag   = f"{bc.Light_Blue_f}[fallback]{R}"
            lbl_s = f"{bc.Light_Blue_f}{label:<10}{R}"
        elif elem_name in rgb_only:
            tag   = f"{bc.Light_Yellow_f}[RGB-coded files only — --rgbFallback nvdec]{R}"
            lbl_s = f"{bc.Light_Yellow_f}{label:<10}{R}"
        elif gst_ok and Gst.ElementFactory.find(elem_name).get_rank() == Gst.Rank.NONE:
            tag   = f"{bc.Dark_Gray_f}[disabled by --decoder {pref}]{R}"
            lbl_s = f"{bc.Dark_Gray_f}{label:<10}{R}"
        else:
            tag   = f"{bc.Light_Yellow_f}[available]{R}"
            lbl_s = f"{bc.Light_Yellow_f}{label:<10}{R}"

        print(f"  {bc.Magenta_f}{prefix}{R}"
              f"{lbl_s}  "
              f"{bc.Dark_Gray_f}{elem_name:<30}{R}  {tag}")

    # ── Hardware categories with no element present ───────────────────────────
    _labels = {'nvdec': 'NVDEC', 'vaapi': 'VA-API'}
    for cat in _HW_ORDER:
        if cat not in available_cats:
            label = _labels[cat]
            print(f"  {bc.Magenta_f}          {R}"
                  f"{bc.Dark_Gray_f}{label:<10}  {'—':<30}  [not available]{R}")

    print(sep)
    print()
