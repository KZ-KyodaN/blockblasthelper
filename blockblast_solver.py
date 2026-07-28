from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


@dataclass
class BoardGeometry:
    left: float
    top: float
    size: float

    @property
    def cell(self) -> float:
        return self.size / 8.0

    @property
    def right(self) -> float:
        return self.left + self.size

    @property
    def bottom(self) -> float:
        return self.top + self.size


@dataclass
class Piece:
    name: str
    cells: list[tuple[int, int]]
    color: tuple[int, int, int, int]
    center_x: float


@dataclass
class Solution:
    full: bool
    path: list[tuple[int, tuple[int, int], list[tuple[str, int]]]]
    remaining: list[int]
    score: tuple[int, int, int]


PALETTE = [
    (255, 135, 30, 135),
    (50, 210, 240, 135),
    (60, 205, 80, 125),
    (80, 125, 255, 135),
    (255, 55, 70, 135),
    (170, 90, 235, 135),
]


def component_boxes(mask: np.ndarray, min_pixels: int = 100) -> list[tuple[int, int, int, int, int]]:
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    boxes = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            stack = [(x, y)]
            seen[y, x] = True
            xs = []
            ys = []
            while stack:
                px, py = stack.pop()
                xs.append(px)
                ys.append(py)
                for nx, ny in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
                    if 0 <= nx < w and 0 <= ny < h and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((nx, ny))
            if len(xs) >= min_pixels:
                boxes.append((len(xs), min(xs), min(ys), max(xs) + 1, max(ys) + 1))
    return boxes


def contrast_mask(image: Image.Image, blur_radius: int = 10, threshold: int = 35) -> np.ndarray:
    blur = image.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    arr = np.asarray(image.convert("RGB")).astype(int)
    bg = np.asarray(blur.convert("RGB")).astype(int)
    return np.abs(arr - bg).max(axis=2) > threshold


def estimate_board_geometry(img: Image.Image) -> BoardGeometry:
    w, h = img.size
    size = w * 0.895
    left = (w - size) / 2.0
    top = h * 0.235
    return BoardGeometry(left=left, top=top, size=size)


def read_board(img: Image.Image, geom: BoardGeometry) -> np.ndarray:
    occupied = np.zeros((8, 8), dtype=bool)
    cell = geom.cell
    for r in range(8):
        for c in range(8):
            pad = max(6, int(cell * 0.13))
            left = int(geom.left + c * cell + pad)
            top = int(geom.top + r * cell + pad)
            right = int(geom.left + (c + 1) * cell - pad)
            bottom = int(geom.top + (r + 1) * cell - pad)
            crop = np.asarray(img.crop((left, top, right, bottom)).convert("RGB")).astype(int)
            mx = crop.max(axis=2)
            mn = crop.min(axis=2)
            bright_colored = (mx > 100) & ((mx - mn) > 25)
            turquoise_blocks = (crop[:, :, 0] < 165) & (crop[:, :, 1] > 170) & (crop[:, :, 2] > 185)
            occupied[r, c] = bright_colored.mean() > 0.12 or turquoise_blocks.mean() > 0.20
    return occupied


def extract_piece_cells(piece_crop: Image.Image, pitch: float) -> list[tuple[int, int]]:
    arr = np.asarray(piece_crop.convert("RGB")).astype(int)
    h, w = arr.shape[:2]
    rows = max(1, min(5, int(round(h / pitch))))
    cols = max(1, min(5, int(round(w / pitch))))
    cells = []
    pitch_x = w / cols
    pitch_y = h / rows
    for r in range(rows):
        for c in range(cols):
            x0 = int(max(0, c * pitch_x + pitch_x * 0.38))
            y0 = int(max(0, r * pitch_y + pitch_y * 0.38))
            x1 = int(min(w, c * pitch_x + pitch_x * 0.62))
            y1 = int(min(h, r * pitch_y + pitch_y * 0.62))
            if x1 <= x0 or y1 <= y0:
                continue
            avg = arr[y0:y1, x0:x1].mean(axis=(0, 1))
            red, green, blue = avg
            blue_tray_bg = blue < 170 and blue > green + 25 and blue > red + 35 and green < 130 and red < 110
            block_like = max(avg) > 100 and (max(avg) - min(avg)) > 35 and not blue_tray_bg
            if block_like:
                cells.append((r, c))
    if not cells:
        return []
    min_r = min(r for r, _ in cells)
    min_c = min(c for _, c in cells)
    return sorted((r - min_r, c - min_c) for r, c in set(cells))


def read_pieces(img: Image.Image, geom: BoardGeometry) -> list[Piece]:
    w, h = img.size
    tray_top = int(min(h - 1, geom.bottom + h * 0.035))
    tray_bottom = int(min(h * 0.91, geom.bottom + h * 0.30))
    crop = img.crop((0, tray_top, w, tray_bottom))
    mask = contrast_mask(crop, blur_radius=10, threshold=35)
    boxes = component_boxes(mask, min_pixels=max(120, int(w * h * 0.00004)))
    pitch = geom.cell * 0.445
    pieces = []
    for _, lx, ty, rx, by in boxes:
        bw = rx - lx
        bh = by - ty
        if not (pitch * 0.65 <= bw <= pitch * 4.2 and pitch * 0.65 <= bh <= pitch * 4.2):
            continue
        if ty < 10:
            continue
        pad = int(max(2, pitch * 0.04))
        piece_crop = crop.crop((max(0, lx - pad), max(0, ty - pad), min(crop.width, rx + pad), min(crop.height, by + pad)))
        cells = extract_piece_cells(piece_crop, pitch)
        if not cells or len(cells) > 9:
            continue
        cx = (lx + rx) / 2.0
        color = PALETTE[len(pieces) % len(PALETTE)]
        pieces.append(Piece(name=f"piece_{len(pieces) + 1}", cells=cells, color=color, center_x=cx))
    pieces.sort(key=lambda p: p.center_x)
    for i, piece in enumerate(pieces):
        piece.name = f"piece_{i + 1}"
        piece.color = PALETTE[i % len(PALETTE)]
    return pieces[:3]


def clear_lines(grid: np.ndarray) -> tuple[np.ndarray, list[tuple[str, int]]]:
    new_grid = grid.copy()
    cleared = []
    rows = [r for r in range(8) if new_grid[r, :].all()]
    cols = [c for c in range(8) if new_grid[:, c].all()]
    for r in rows:
        new_grid[r, :] = False
        cleared.append(("row", r))
    for c in cols:
        new_grid[:, c] = False
        cleared.append(("col", c))
    return new_grid, cleared


def can_place(grid: np.ndarray, cells: list[tuple[int, int]], pos: tuple[int, int]) -> bool:
    row, col = pos
    for dr, dc in cells:
        rr = row + dr
        cc = col + dc
        if rr < 0 or rr >= 8 or cc < 0 or cc >= 8 or grid[rr, cc]:
            return False
    return True


def all_places(grid: np.ndarray, cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(r, c) for r in range(8) for c in range(8) if can_place(grid, cells, (r, c))]


def place(grid: np.ndarray, cells: list[tuple[int, int]], pos: tuple[int, int]) -> tuple[np.ndarray, list[tuple[str, int]]]:
    new_grid = grid.copy()
    for dr, dc in cells:
        new_grid[pos[0] + dr, pos[1] + dc] = True
    return clear_lines(new_grid)


def largest_empty_rectangle_score(grid: np.ndarray) -> int:
    best = 0
    for r in range(8):
        for c in range(8):
            for hh in range(1, 9 - r):
                for ww in range(1, 9 - c):
                    area = hh * ww
                    if area > best and not grid[r : r + hh, c : c + ww].any():
                        best = area
    return best


def solve_grid(grid: np.ndarray, pieces: list[Piece]) -> Solution:
    complete = []
    partial = []

    def dfs(cur_grid: np.ndarray, remaining: list[int], path: list[tuple[int, tuple[int, int], list[tuple[str, int]]]], clears: int):
        score = (len(path), clears, int((~cur_grid).sum()) + largest_empty_rectangle_score(cur_grid))
        partial.append((score, path, remaining, cur_grid.copy()))
        if not remaining:
            complete.append(((clears, int((~cur_grid).sum()), largest_empty_rectangle_score(cur_grid)), path, cur_grid.copy()))
            return
        for idx in remaining:
            for pos in all_places(cur_grid, pieces[idx].cells):
                next_grid, just_cleared = place(cur_grid, pieces[idx].cells, pos)
                dfs(next_grid, [x for x in remaining if x != idx], path + [(idx, pos, just_cleared)], clears + len(just_cleared))

    dfs(grid, list(range(len(pieces))), [], 0)
    complete.sort(key=lambda item: item[0], reverse=True)
    if complete:
        score, path, _ = complete[0]
        return Solution(full=True, path=path, remaining=[], score=score)
    partial.sort(key=lambda item: item[0], reverse=True)
    score, path, remaining, _ = partial[0]
    return Solution(full=False, path=path, remaining=remaining, score=score)


def cell_box(geom: BoardGeometry, row: int, col: int, pad: float = 5.0) -> tuple[float, float, float, float]:
    cell = geom.cell
    return (
        geom.left + col * cell + pad,
        geom.top + row * cell + pad,
        geom.left + (col + 1) * cell - pad,
        geom.top + (row + 1) * cell - pad,
    )


def draw_solution(img: Image.Image, geom: BoardGeometry, pieces: list[Piece], solution: Solution, out_path: str | Path) -> None:
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for i in range(9):
        x = geom.left + i * geom.cell
        y = geom.top + i * geom.cell
        draw.line((x, geom.top, x, geom.bottom), fill=(255, 255, 255, 115), width=max(2, int(geom.cell * 0.018)))
        draw.line((geom.left, y, geom.right, y), fill=(255, 255, 255, 115), width=max(2, int(geom.cell * 0.018)))

    cleared_cols = set()
    cleared_rows = set()
    for _, _, cleared in solution.path:
        for kind, idx in cleared:
            if kind == "col":
                cleared_cols.add(idx)
            else:
                cleared_rows.add(idx)
    for c in cleared_cols:
        draw.rectangle(cell_box(geom, 0, c, pad=2)[:2] + cell_box(geom, 7, c, pad=2)[2:], outline=(255, 255, 70, 255), width=max(4, int(geom.cell * 0.04)))
    for r in cleared_rows:
        draw.rectangle(cell_box(geom, r, 0, pad=2)[:2] + cell_box(geom, r, 7, pad=2)[2:], outline=(255, 255, 70, 255), width=max(4, int(geom.cell * 0.04)))

    for step, (piece_idx, pos, cleared) in enumerate(solution.path, start=1):
        piece = pieces[piece_idx]
        for dr, dc in piece.cells:
            rr = pos[0] + dr
            cc = pos[1] + dc
            draw.rounded_rectangle(cell_box(geom, rr, cc, pad=max(5, geom.cell * 0.055)), radius=int(geom.cell * 0.10), fill=piece.color, outline=(255, 255, 255, 245), width=max(3, int(geom.cell * 0.035)))
            cx = geom.left + (cc + 0.5) * geom.cell
            cy = geom.top + (rr + 0.5) * geom.cell
            draw.text((cx - geom.cell * 0.06, cy - geom.cell * 0.10), str(step), fill=(255, 255, 255, 255))
        label = f"{step}: {piece.name}"
        if cleared:
            label += " clears " + ",".join(f"{kind}{idx + 1}" for kind, idx in cleared)
        draw.text((geom.left + pos[1] * geom.cell + 4, max(geom.top + 4, geom.top + (pos[0] - 0.23) * geom.cell)), label, fill=(255, 255, 255, 255))

    y0 = min(base.height - 210, int(geom.bottom + geom.cell * 0.45))
    draw.rectangle((geom.left, y0, geom.right, y0 + 150), fill=(0, 0, 0, 165))
    title = "FULL SOLUTION" if solution.full else "NO FULL SOLUTION - BEST PARTIAL"
    draw.text((geom.left + 18, y0 + 18), title, fill=(255, 255, 255, 255))
    for i, line in enumerate(format_solution(solution, pieces).splitlines()[:4]):
        draw.text((geom.left + 18, y0 + 48 + i * 24), line, fill=(235, 240, 255, 255))
    Image.alpha_composite(base, overlay).convert("RGB").save(out_path)


def format_solution(solution: Solution, pieces: list[Piece]) -> str:
    if not solution.path:
        return "No legal move found."
    lines = []
    for step, (piece_idx, pos, cleared) in enumerate(solution.path, start=1):
        extra = ""
        if cleared:
            extra = " | clears " + ", ".join(f"{kind} {idx + 1}" for kind, idx in cleared)
        lines.append(f"{step}. {pieces[piece_idx].name}: top-left R{pos[0] + 1} C{pos[1] + 1}{extra}")
    if not solution.full:
        lines.append("Remaining: " + ", ".join(pieces[i].name for i in solution.remaining))
    return "\n".join(lines)


def solve_image(image_path: str | Path, out_path: str | Path) -> tuple[Solution, list[Piece], np.ndarray]:
    img = Image.open(image_path).convert("RGB")
    geom = estimate_board_geometry(img)
    grid = read_board(img, geom)
    pieces = read_pieces(img, geom)
    if len(pieces) != 3:
        raise RuntimeError(f"Expected 3 pieces, detected {len(pieces)}. Try a full screenshot without cropping the tray.")
    solution = solve_grid(grid, pieces)
    draw_solution(img, geom, pieces, solution, out_path)
    return solution, pieces, grid


def main() -> None:
    parser = argparse.ArgumentParser(description="Solve a Block Blast screenshot and draw placement hints.")
    parser.add_argument("image", help="Path to screenshot")
    parser.add_argument("-o", "--output", default="blockblast_solution.png", help="Output annotated image")
    args = parser.parse_args()
    solution, pieces, _ = solve_image(args.image, args.output)
    print("Full solution found" if solution.full else "No full solution; best partial line")
    print(format_solution(solution, pieces))
    print(Path(args.output).resolve())


if __name__ == "__main__":
    main()
