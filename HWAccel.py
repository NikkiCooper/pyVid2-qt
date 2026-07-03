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
"""

import os
from Bcolors import Bcolors

bc = Bcolors()

# Ordered probe list: (element_name, display_label, category)
# First match per category is used; order determines tie-breaking within a category.
'''
_HEVC_CANDIDATES = [
    ('nvh265dec',            'NVDEC',    'nvdec'),
    ('vulkanh265device1dec', 'Vulkan',   'vulkan'),
    ('vah265dec',            'VA-API',   'vaapi'),
    ('vaapih265dec',         'VA-API',   'vaapi'),
    ('libde265dec',          'libde265', 'software'),
    ('avdec_h265',           'FFmpeg',   'software'),
]
'''
_HEVC_CANDIDATES = [
    # NVDEC (Nvidia)
    ('nvh265dec', 'NVDEC', 'nvdec'),
    ('nvh264dec', 'NVDEC', 'nvdec'),

    # Vulkan
    ('vulkanh265device1dec', 'Vulkan', 'vulkan'),
    ('vulkanh264device1dec', 'Vulkan', 'vulkan'),

    # VA-API (Modern & Legacy variants)
    ('vah265dec', 'VA-API', 'vaapi'),
    ('vah264dec', 'VA-API', 'vaapi'),
    ('vaapih265dec', 'VA-API', 'vaapi'),
    ('vaapih264dec', 'VA-API', 'vaapi'),

    # Software Fallbacks
    ('libde265dec', 'libde265', 'software'),
    ('avdec_h265', 'FFmpeg', 'software'),
    ('avdec_h264', 'FFmpeg', 'software'),
]

# Hardware categories shown in the "not available" section if absent
_HW_ORDER = ['nvdec', 'vulkan', 'vaapi']


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

def _probe(Gst):
    """
    Return list of (elem_name, label, category, rank) for available HEVC decoders.
    Only the first available match per category is included.
    """
    results = []
    seen = set()
    for elem_name, label, category in _HEVC_CANDIDATES:
        if category in seen:
            continue
        factory = Gst.ElementFactory.find(elem_name)
        if factory:
            results.append((elem_name, label, category, factory.get_rank()))
            seen.add(category)
    return results


def _demote(Gst, by_cat, *categories):
    """Set GStreamer rank to NONE for the named categories."""
    for cat in categories:
        if cat in by_cat:
            factory = Gst.ElementFactory.find(by_cat[cat][0])
            if factory:
                factory.set_rank(Gst.Rank.NONE)


# ── Public API ─────────────────────────────────────────────────────────────────

def setup_decoder(pref='auto'):
    """
    Configure GStreamer decoder ranks based on the --decoder preference.

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

    # category → (elem_name, label, rank)
    by_cat = {cat: (elem, label, rank) for elem, label, cat, rank in available}

    if pref == 'auto':
        # Let GStreamer decide — highest registered rank wins
        best = max(available, key=lambda x: x[3])
        return best[1], available

    elif pref == 'nvdec':
        if 'nvdec' in by_cat:
            _demote(Gst, by_cat, 'vulkan', 'vaapi')
            return by_cat['nvdec'][1], available
        print(f"{bc.Yellow_f}--decoder nvdec: NVDEC not available — falling back to auto{bc.RESET}")
        return setup_decoder('auto')

    elif pref == 'vulkan':
        if 'vulkan' in by_cat:
            _demote(Gst, by_cat, 'nvdec', 'vaapi')
            return by_cat['vulkan'][1], available
        print(f"{bc.Yellow_f}--decoder vulkan: Vulkan decoder not available — falling back to auto{bc.RESET}")
        return setup_decoder('auto')

    elif pref == 'vaapi':
        if 'vaapi' in by_cat:
            # Force the Intel driver architecture
            if not os.environ.get('LIBVA_DRIVER_NAME'):
                os.environ['LIBVA_DRIVER_NAME'] = 'iHD'
            _demote(Gst, by_cat, 'nvdec', 'vulkan')
            return by_cat['vaapi'][1], available
        print(f"{bc.Yellow_f}--decoder vaapi: VA-API not available — falling back to auto{bc.RESET}")
        return setup_decoder('auto')

    elif pref == 'software':
        _demote(Gst, by_cat, 'nvdec', 'vulkan', 'vaapi')
        sw = next((r for r in available if r[2] == 'software'), None)
        return (sw[1] if sw else 'Software'), available

    return 'Unknown', available


def print_startup_info(version, active_label, available):
    """Print version banner and decoder status table to stdout."""
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
        else:
            tag   = f"{bc.Light_Yellow_f}[available]{R}"
            lbl_s = f"{bc.Light_Yellow_f}{label:<10}{R}"

        print(f"  {bc.Magenta_f}{prefix}{R}"
              f"{lbl_s}  "
              f"{bc.Dark_Gray_f}{elem_name:<30}{R}  {tag}")

    # ── Hardware categories with no element present ───────────────────────────
    _labels = {'nvdec': 'NVDEC', 'vulkan': 'Vulkan', 'vaapi': 'VA-API'}
    for cat in _HW_ORDER:
        if cat not in available_cats:
            label = _labels[cat]
            print(f"  {bc.Magenta_f}          {R}"
                  f"{bc.Dark_Gray_f}{label:<10}  {'—':<30}  [not available]{R}")

    print(sep)
    print()
