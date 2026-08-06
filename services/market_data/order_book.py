from services.shared.config import ORDER_BOOK_DEPTH


def _parse_levels(raw_levels, reverse=False):
    levels = []
    if not raw_levels:
        return levels

    if isinstance(raw_levels[0], (list, tuple)):
        for entry in raw_levels:
            price = float(entry[0])
            size = float(entry[1])
            if size > 0:
                levels.append([price, size])
    else:
        for i in range(0, len(raw_levels), 2):
            price = float(raw_levels[i])
            size = float(raw_levels[i + 1])
            if size > 0:
                levels.append([price, size])

    levels.sort(key=lambda x: x[0], reverse=reverse)
    return levels[:ORDER_BOOK_DEPTH]


def apply_snapshot(book, bids_raw, asks_raw):
    book["bids"] = _parse_levels(bids_raw, reverse=True)
    book["asks"] = _parse_levels(asks_raw, reverse=False)


def apply_update(book, side, price, size):
    levels = book["bids"] if side == "buy" else book["asks"]
    reverse = side == "buy"
    price = float(price)
    size = float(size)

    updated = False
    for i, (p, s) in enumerate(levels):
        if p == price:
            if size == 0:
                levels.pop(i)
            else:
                levels[i] = [price, size]
            updated = True
            break

    if not updated and size > 0:
        levels.append([price, size])
        levels.sort(key=lambda x: x[0], reverse=reverse)

    key = "bids" if side == "buy" else "asks"
    book[key] = levels[:ORDER_BOOK_DEPTH]
