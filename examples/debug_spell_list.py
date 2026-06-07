"""
Diagnostic tool for SpellListControl memory layout.

Reads spell names from AllPageSpellList using the confirmed offsets:
  - Vector at offset 0x300 (stride 0x78, SpellListControlSpellEntry array)
  - graphical_spell pointer at offset 0x00 within each entry
  - spell_template pointer at offset 0x78 within GraphicalSpell
  - Spell name at offset 96 within SpellTemplate

UI path (as of 2026-06):
  WorldView -> DeckConfiguration -> DeckConfigurationWindow -> DeckPage -> AllPageSpellList

Prerequisites:
  - Wizard101 must be running
  - Spellbook does NOT need to be open (script opens it)

Usage:
  py debug_spell_list.py
"""

import asyncio

from wizwalker import ClientHandler
from wizwalker.extensions.scripting.utils import _maybe_get_named_window
from wizwalker.memory.memory_objects.window import DynamicSpellListControl



async def click_by_path(client, path: list[str], label: str) -> bool:
    print(f"  Clicking: {' -> '.join(path)}")
    try:
        win = client.root_window
        for step in path:
            win = await _maybe_get_named_window(win, step)
        async with client.mouse_handler:
            await client.mouse_handler.click_window(win)
        print(f"  OK: {label}")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def main():
    handler = ClientHandler()
    clients = handler.get_new_clients()
    if not clients:
        print("No Wizard101 client found. Start the game first.")
        return

    client = clients[0]

    try:
        print("Activating hooks...")
        await client.hook_handler.activate_root_window_hook()
        await client.hook_handler.activate_render_context_hook()
        print("Ready.\n")

        print("Opening deck page...")
        await click_by_path(client, ["WorldView", "windowHUD", "btnSpellbook"], "open spellbook")
        await asyncio.sleep(1)
        await click_by_path(client, ["WorldView", "DeckConfiguration", "Deck"], "open deck tab")
        await asyncio.sleep(1)
        print()

        deck_config = await _maybe_get_named_window(client.root_window, "DeckConfiguration")
        dcw = await _maybe_get_named_window(deck_config, "DeckConfigurationWindow")
        deck_page = await _maybe_get_named_window(dcw, "DeckPage")
        spell_list_win = await _maybe_get_named_window(deck_page, "AllPageSpellList")

        base_addr = await spell_list_win.read_base_address()
        print(f"AllPageSpellList base address: 0x{base_addr:X}\n")

        ctrl = DynamicSpellListControl(client.hook_handler, base_addr)

        print("Reading spell entries via production API...")
        entries = await ctrl.spell_entries()
        print(f"  {len(entries)} entries returned\n")

        named = 0
        errors = 0
        for i, entry in enumerate(entries):
            try:
                gfx = await entry.graphical_spell()
                if gfx is None:
                    print(f"  [{i:>3}] graphical_spell is None")
                    continue
                tmpl = await gfx.spell_template()
                if tmpl is None:
                    print(f"  [{i:>3}] spell_template is None  (gfx=0x{await gfx.read_base_address():X})")
                    continue
                name = await tmpl.name()
                max_c = await entry.max_copies()
                cur_c = await entry.current_copies()
                print(f"  [{i:>3}] {name!r:<30}  max={max_c}  cur={cur_c}")
                named += 1
            except Exception as e:
                print(f"  [{i:>3}] ERROR: {e}")
                errors += 1

        print(f"\n{named} spell(s) named, {errors} error(s).")

    except ValueError as e:
        print(f"ERROR: {e}")
    finally:
        print("\nClosing...")
        await handler.close()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
