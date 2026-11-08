"""Actual Lua producer → Python decoder; optional native Quartz capture.

uv run --no-sync --with lupa==2.6 python tests/smoke_wow_wire.py --capture
Uses synthetic game API values, never the player's private screen as an artifact.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from game import decode


def show(path):
    from AppKit import NSWindow, NSImageView, NSImage, NSMakeRect, NSBackingStoreBuffered
    from PyObjCTools import AppHelper
    from overlay import activate_app
    activate_app()
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(500, 400, 256, 32), 0, NSBackingStoreBuffered, False)
    window.setReleasedWhenClosed_(False)
    window.setLevel_(26)
    view = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, 256, 32))
    view.setImage_(NSImage.alloc().initWithContentsOfFile_(path))
    window.setContentView_(view)
    window.orderFrontRegardless()
    AppHelper.callLater(.3, lambda: print('ready', flush=True))
    AppHelper.runEventLoop()


def producer():
    from lupa import LuaRuntime
    lua = LuaRuntime(encoding=None)
    lua.execute((ROOT / 'addons/WhaleBridge/Protocol.lua').read_bytes())
    lua.execute(b'''
        hidden = {}; combat = false; cells = {}; visible = {}
        function issecretvalue(v) return rawequal(v, hidden) end
        function issecrettable(v) return rawequal(v, hidden) end
        function time() return NOW end
        function InCombatLockdown() return combat end
        function IsLoggedIn() return true end
        function GetBuildInfo() return '1.60.1', '70862' end
        function GetZoneText() return 'Elwynn' end
        function GetSubZoneText() return 'Goldshire' end
        function UnitLevel() return 12 end
        function UnitClass() return 'Mage', 'MAGE' end
        function UnitGUID() return 'Creature-0-1-2-3-12345-abcdef' end
        function UnitName() return hidden end
        C_Map = {
          GetBestMapForUnit = function() return 37 end,
          GetPlayerMapPosition = function() return {GetXY=function() return .421, .652 end} end
        }
        C_QuestLog = {
          GetSelectedQuest = function() return 7 end,
          GetNumQuestLogEntries = function() return 1 end,
          GetInfo = function() return {questID=7, title=TITLE, isHeader=false} end,
          IsComplete = function() return false end,
          GetQuestObjectives = function() return {{text=OBJECTIVE}, {text=hidden}} end
        }
        UIParent = {GetEffectiveScale=function() return 1 end}
        function CreateFrame()
          return setmetatable({CreateTexture=function()
            local i = #cells + 1; cells[i] = {0,0,0}
            return setmetatable({SetColorTexture=function(_,r,g,b) cells[i]={r*255,g*255,b*255} end,
              Show=function() visible[i]=true end, Hide=function() visible[i]=false end}, {__index=function() return function() end end})
          end}, {__index=function() return function() end end})
        end
        SlashCmdList = {}
        C_Timer = {NewTicker=function(_, fn) tick=fn end}
    ''')
    lua.globals().NOW = int(time.time())
    lua.globals().TITLE = '找“人”\\线索'.encode()
    lua.globals().OBJECTIVE = '已找到 1/3 位居民'.encode()
    lua.execute((ROOT / 'addons/WhaleBridge/WhaleBridge.lua').read_bytes())
    assert lua.globals().visible[1] is not True
    lua.globals().SlashCmdList.WHALEBRIDGE(b'on')
    def image():
        colors = [[lua.globals().cells[i][c] for c in (1, 2, 3)] for i in range(1, 2049)]
        return Image.fromarray(np.round(colors).astype(np.uint8).reshape(16, 128, 3)).resize((256, 32), Image.Resampling.NEAREST)
    decoded = decode(image())
    assert decoded and decoded['target'] == {'id': 12345}, decoded
    assert decoded['selectedQuest']['title'] == '找“人”\\线索', decoded
    assert decoded['selectedQuest']['objectives'] == ['已找到 1/3 位居民'], decoded
    assert decoded['x'] == 42.1 and decoded['y'] == 65.2, decoded
    assert lua.globals().visible[1] is True and lua.globals().visible[2048] is False
    lua.globals().combat = True
    lua.globals().tick()
    fighting = decode(image())
    assert fighting['inCombat'] and 'x' not in fighting and 'target' not in fighting and 'quests' not in fighting, fighting
    lua.globals().combat = False
    lua.globals().tick()
    return image(), decoded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', action='store_true')
    parser.add_argument('--show')
    args = parser.parse_args()
    if args.show:
        show(args.show)
        return
    image, expected = producer()
    print('Actual Lua producer: Chinese/escapes, IDs, coordinates, secret-value omission and combat suppression passed.')
    if args.capture:
        from capture import grab
        with tempfile.TemporaryDirectory(prefix='whale-wire-') as folder:
            path = Path(folder) / 'synthetic-panel.png'
            image.save(path)
            child = subprocess.Popen([sys.executable, __file__, '--show', str(path)], stdout=subprocess.PIPE, text=True)
            try:
                assert child.stdout.readline().strip() == 'ready'
                time.sleep(.3)
                sampled = grab()
                # Synthetic producer is a fixed image, not a ticking game client.
                result = decode(sampled, now=expected['sampledAt'])
                assert result and result['selectedQuest'] == expected['selectedQuest'], result
                print('Real native window → overlay-excluding Quartz capture → calibrated decoder passed.')
            finally:
                child.terminate()
                child.wait()


if __name__ == '__main__':
    main()
