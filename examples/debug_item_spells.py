"""
Diagnostic: does ItemSpells show only the current page or all item cards?

Reads names by hovering over each slot and capturing the GraphicalSpellWindow
tooltip — this works regardless of DeckListControl memory offsets.

Reads page 1, clicks NextItemSpells, reads page 2, then compares.

Prerequisites:
  - Wizard101 must be running
  - Character must have item cards that span more than one page (>16 cards)

Usage:
  py debug_item_spells.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wizwalker import ClientHandler
from wizwalker.extensions.scripting.utils import _maybe_get_named_window
from wizwalker.memory.memory_objects.window import DynamicGraphicalSpellWindow
from wizwalker.utils import Rectangle


def divide_rectangle(rect: Rectangle, columns: int, rows: int) -> list[Rectangle]:
    width = rect.x2 - rect.x1
    height = rect.y2 - rect.y1
    sub_w = width / columns
    sub_h = height / rows
    result = []
    for r in range(rows):
        for c in range(columns):
            result.append(Rectangle(
                int(rect.x1 + c * sub_w),
                int(rect.y1 + r * sub_h),
                int(rect.x1 + (c + 1) * sub_w),
                int(rect.y1 + (r + 1) * sub_h),
            ))
    return result


async def read_visible_item_names(client) -> list[str]:
    """Hover over each slot in the 8×2 ItemSpells grid and read the name from
    the GraphicalSpellWindow that appears in the world view on hover."""
    item_win = await _maybe_get_named_window(client.root_window, "ItemSpells")
    rect = await item_win.scale_to_client()
    slots = divide_rectangle(rect, columns=8, rows=2)

    world_view = await client.get_world_view_window()
    names = []

    async with client.mouse_handler:
        for slot in slots:
            await client.mouse_handler.set_mouse_position(*slot.center())
            await asyncio.sleep(0.07)

            children = await world_view.children()
            for child in children:
                try:
                    type_name = await child.maybe_read_type_name()
                    if type_name != "GraphicalSpellWindow":
                        continue
                    gfx_win = DynamicGraphicalSpellWindow(
                        client.hook_handler, await child.read_base_address()
                    )
                    gfx = await gfx_win.graphical_spell()
                    if not gfx:
                        continue
                    tmpl = await gfx.spell_template()
                    if not tmpl:
                        continue
                    name = await tmpl.name()
                    if name:
                        names.append(name)
                        break
                except Exception:
                    pass

    return names


async def main():
    handler = ClientHandler()
    clients = handler.get_new_clients()
    if not clients:
        print("No Wizard101 client found.")
        return

    client = clients[0]

    try:
        print("Activating hooks...")
        await client.hook_handler.activate_root_window_hook()
        await client.hook_handler.activate_render_context_hook()

        # Open spellbook / deck page if not already open
        try:
            deck_config = await _maybe_get_named_window(client.root_window, "DeckConfiguration")
        except ValueError:
            print("Opening spellbook...")
            async with client.mouse_handler:
                btn = await _maybe_get_named_window(client.root_window, "btnSpellbook")
                await client.mouse_handler.click_window(btn)
            await asyncio.sleep(1)
            deck_config = await _maybe_get_named_window(client.root_window, "DeckConfiguration")

        deck_btn = await _maybe_get_named_window(deck_config, "Deck")
        async with client.mouse_handler:
            await client.mouse_handler.click_window(deck_btn)
        await asyncio.sleep(0.5)

        # Page 1
        print("Reading page 1 (hover scan)...")
        page1_names = await read_visible_item_names(client)
        print(f"  {len(page1_names)} cards visible:")
        for n in page1_names:
            print(f"    {n}")

        # Find NextItemSpells
        try:
            next_btn = await _maybe_get_named_window(client.root_window, "NextItemSpells")
        except ValueError:
            print("\nNextItemSpells not in UI tree — only one page.")
            return

        print(f"\nNextItemSpells: visible={await next_btn.is_visible()}  "
              f"grayed={await next_btn.is_control_grayed()}")

        print("Clicking NextItemSpells...")
        async with client.mouse_handler:
            await client.mouse_handler.click_window(next_btn)
        await asyncio.sleep(0.5)

        # Page 2
        print("\nReading page 2 (hover scan)...")
        page2_names = await read_visible_item_names(client)
        print(f"  {len(page2_names)} cards visible:")
        for n in page2_names:
            print(f"    {n}")

        # Analysis
        print("\n--- Analysis ---")
        all_names = page1_names + page2_names
        unique = set(all_names)
        overlap = [n for n in page2_names if n in page1_names]

        print(f"Page 1 ({len(page1_names)} cards): {page1_names}")
        print(f"Page 2 ({len(page2_names)} cards): {page2_names}")
        print(f"Overlap: {overlap}")

        if page1_names == page2_names:
            print("\n=> Pages show IDENTICAL names — NextItemSpells may not have worked.")
        elif overlap:
            print(f"\n=> {len(overlap)} shared names — partial overlap (sliding window?).")
        else:
            print(f"\n=> No overlap — pages show distinct sets of cards.")
            print(f"   Total across both pages: {len(unique)} unique card types.")

    finally:
        print("\nClosing...")
        await handler.close()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
