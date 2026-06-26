# -*- coding: utf-8 -*-
"""srwk_rom.py — thin ndspy wrapper for reading/replacing files in the SRW K rom."""
import ndspy.rom

def _names(rom):
    names = {}
    def rec(folder, prefix):
        for i, fname in enumerate(folder.files):
            names[folder.firstID + i] = prefix + fname
        for sub_name, sub in folder.folders:
            rec(sub, prefix + sub_name + "/")
    rec(rom.filenames, "")
    return names

class Rom:
    def __init__(self, path):
        self.path = path
        self.rom = ndspy.rom.NintendoDSRom.fromFile(path)
        self.names = _names(self.rom)
        self.ids = {v: k for k, v in self.names.items()}

    def get(self, name):
        return self.rom.files[self.ids[name]]

    def set(self, name, data):
        self.rom.files[self.ids[name]] = data

    def set_arm9(self, data):
        self.rom.arm9 = data

    def get_arm9(self):
        return self.rom.arm9

    def set_overlay_file(self, file_id, data):
        # overlay files are stored as files 0..91
        self.rom.files[file_id] = data

    def save(self, out_path):
        self.rom.saveToFile(out_path)
