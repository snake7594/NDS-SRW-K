# -*- coding: utf-8 -*-
"""Prepare the user's edited logo for import: resize to 256x224 and turn the near
-black background into transparency."""
import numpy as np
from PIL import Image
T = 20
im = Image.open('_user_logo.png').convert('RGB').resize((256, 224), Image.LANCZOS)
rgb = np.array(im)
alpha = np.where(rgb.max(axis=2) > T, 255, 0).astype(np.uint8)
out = np.dstack([rgb, alpha])
Image.fromarray(out, 'RGBA').save('_user_canvas.png')
print('saved _user_canvas.png  opaque px:', int((alpha > 0).sum()))
