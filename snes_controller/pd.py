##
## SNES / NES Controller Decoder for sigrok / PulseView
##
## Protocol:
##   LATCH  — active-high pulse (~12 µs) latches all button states into the
##             shift register.  DATA is valid for bit 0 as soon as LATCH falls.
##   CLK    — 15 (NES: 7) additional falling edges clock out bits 1-15.
##   DATA   — active-low serial stream; 0 = button pressed.
##
## SNES bit order (LSB first):
##   0  B        8  A
##   1  Y        9  X
##   2  Select  10  L
##   3  Start   11  R
##   4  Up      12-15  (always 1, unused)
##   5  Down
##   6  Left
##   7  Right
##
## NES bit order:
##   0  A   4  Up
##   1  B   5  Down
##   2  Sel 6  Left
##   3  Sta 7  Right
##

import sigrokdecode as srd

SNES_BUTTONS = [
    'B', 'Y', 'Select', 'Start', 'Up', 'Down', 'Left', 'Right',
    'A', 'X', 'L', 'R', None, None, None, None,
]

NES_BUTTONS = [
    'A', 'B', 'Select', 'Start', 'Up', 'Down', 'Left', 'Right',
]

ANN_BIT    = 0
ANN_BUTTON = 1
ANN_FRAME  = 2
ANN_LATCH  = 3


class Decoder(srd.Decoder):
    api_version = 3
    id          = 'snes_controller'
    name        = 'SNES controller'
    longname    = 'Super Nintendo / NES gamepad'
    desc        = 'SNES/NES gamepad serial protocol decoder (LATCH/CLK/DATA).'
    license     = 'gplv2+'
    inputs      = ['logic']
    outputs     = []
    tags        = ['Retro computing']

    channels = (
        {'id': 'latch', 'name': 'LATCH', 'desc': 'Latch signal (active high)'},
        {'id': 'clk',   'name': 'CLK',   'desc': 'Clock'},
        {'id': 'data',  'name': 'DATA',  'desc': 'Serial data (active low)'},
    )

    options = (
        {'id': 'variant', 'desc': 'Controller variant',
         'default': 'SNES', 'values': ('SNES', 'NES')},
        {'id': 'clk_edge', 'desc': 'Sample DATA on clock edge',
         'default': 'falling', 'values': ('falling', 'rising')},
    )

    annotations = (
        ('bit',    'Bit value'),        # 0
        ('button', 'Button press'),     # 1
        ('frame',  'Full frame'),       # 2
        ('latch',  'Latch pulse'),      # 3
    )

    annotation_rows = (
        ('bits',    'Bits',    (ANN_BIT,)),
        ('buttons', 'Buttons', (ANN_BUTTON,)),
        ('frames',  'Frames',  (ANN_FRAME,)),
        ('latch',   'Latch',   (ANN_LATCH,)),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        pass

    def start(self):
        self.out_ann = self.register(srd.OUTPUT_ANN)
        variant = self.options['variant']
        self.buttons  = SNES_BUTTONS if variant == 'SNES' else NES_BUTTONS
        self.num_bits = len(self.buttons)
        self.edge     = 'f' if self.options['clk_edge'] == 'falling' else 'r'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _put(self, ss, es, ann_id, texts):
        self.put(ss, es, self.out_ann, [ann_id, texts])

    # ------------------------------------------------------------------
    # Main decode loop
    # ------------------------------------------------------------------

    def decode(self):
        while True:
            # ── Wait for LATCH rising edge ─────────────────────────────
            self.wait({0: 'r'})
            latch_rise = self.samplenum

            # ── Wait for LATCH falling edge ────────────────────────────
            self.wait({0: 'f'})
            latch_fall = self.samplenum

            self._put(latch_rise, latch_fall, ANN_LATCH, ['LATCH', 'L'])

            frame_start   = latch_fall
            frame_end     = latch_fall
            bit_spans     = []   # [(ss, es, bit_index, data_value), ...]

            # ── Bit 0: DATA is already valid right after LATCH falls ───
            # Sample DATA on the first CLK edge (the controller has already
            # set it up during the LATCH pulse).
            pins = self.wait({1: self.edge})
            bit_ss = latch_fall
            bit_es = self.samplenum
            bit_spans.append((bit_ss, bit_es, 0, pins[2]))

            # ── Bits 1 … num_bits-1: one CLK edge each ─────────────────
            for i in range(1, self.num_bits):
                prev_es = self.samplenum
                pins = self.wait({1: self.edge})
                bit_ss = prev_es
                bit_es = self.samplenum
                bit_spans.append((bit_ss, bit_es, i, pins[2]))

            frame_end = self.samplenum

            # ── Emit annotations ───────────────────────────────────────
            pressed_names = []

            for (ss, es, idx, raw) in bit_spans:
                # Data is active-low: raw 0 → pressed
                pressed = (raw == 0)
                bit_val = 0 if pressed else 1
                self._put(ss, es, ANN_BIT, [str(bit_val)])

                name = self.buttons[idx]
                if pressed and name is not None:
                    self._put(ss, es, ANN_BUTTON, [name, name[0]])
                    pressed_names.append(name)

            summary = ' + '.join(pressed_names) if pressed_names else '(none)'
            self._put(frame_start, frame_end, ANN_FRAME,
                      ['Buttons: ' + summary, summary])
