#!/usr/bin/env python3
"""Generate travels/<faction>/<source>/<destination>/duration.txt from DataFlights.lua.

Reads the CLASSIC section of DataFlights.lua and creates, for each faction
(Horde, Alliance), one folder per source, one folder per destination, and a
duration.txt containing just the flight duration in seconds.
"""
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LUA_PATH = os.path.join(ROOT, "DataFlights.lua")
OUT_DIR = os.path.join(ROOT, "travels")


def tokenize(text: str):
    """Tokenize the tiny Lua subset used by DataFlights.lua."""
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == '\\' and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            tokens.append(('str', ''.join(buf)))
            i = j + 1
            continue
        if c in '{}[]=,':
            tokens.append((c, c))
            i += 1
            continue
        m = re.match(r'-?\d+', text[i:])
        if m:
            tokens.append(('num', int(m.group(0))))
            i += len(m.group(0))
            continue
        # Anything unrecognised (e.g. comments) is skipped.
        i += 1
    return tokens


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def advance(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def expect_symbol(self, symbol):
        tok = self.peek()
        if tok is None or tok != (symbol, symbol):
            raise ValueError(f"Expected '{symbol}', got {tok}")
        self.pos += 1
        return tok

    def parse_value(self):
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected end of input")
        if tok[0] == 'num':
            self.pos += 1
            return tok[1]
        if tok[1] == '{':
            return self.parse_table()
        raise ValueError(f"Unexpected token {tok}")

    def parse_table(self):
        self.expect_symbol('{')
        result = {}
        while True:
            tok = self.peek()
            if tok is None:
                raise ValueError("Unclosed table")
            if tok[1] == '}':
                self.pos += 1
                return result
            if tok[1] == '[':
                self.pos += 1
                key_tok = self.advance()
                if key_tok is None or key_tok[0] != 'str':
                    raise ValueError(f"Expected string key, got {key_tok}")
                self.expect_symbol(']')
                self.expect_symbol('=')
                value = self.parse_value()
                result[key_tok[1]] = value
                # Optional trailing comma before the next field or '}'.
                nxt = self.peek()
                if nxt is not None and nxt[1] == ',':
                    self.pos += 1
                continue
            raise ValueError(f"Unexpected token {tok}")


def extract_classic_block(content: str) -> str:
    marker = 'FlyTravelTimes.FlightDB["CLASSIC"]'
    start = content.index(marker)
    brace_start = content.index('{', start)
    depth = 0
    for i in range(brace_start, len(content)):
        if content[i] == '{':
            depth += 1
        elif content[i] == '}':
            depth -= 1
            if depth == 0:
                return content[brace_start:i + 1]
    raise ValueError("Could not find the closing brace of the CLASSIC table")


def main() -> None:
    with open(LUA_PATH, encoding="utf-8") as f:
        content = f.read()

    classic_block = extract_classic_block(content)
    db = Parser(tokenize(classic_block)).parse_table()

    # db: faction -> source -> destination -> duration (seconds)
    #
    # Each faction is written to its own top-level folder (travels/horde and
    # travels/alliance). Keeping factions separate preserves the original data
    # exactly, including the cases where Horde and Alliance disagree on a route.
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)

    total_edges = 0
    for faction, sources in db.items():
        faction_dir = os.path.join(OUT_DIR, faction.lower())
        faction_edges = 0
        for source in sorted(sources):
            source_dir = os.path.join(faction_dir, source)
            for destination in sorted(sources[source]):
                dest_dir = os.path.join(source_dir, destination)
                os.makedirs(dest_dir, exist_ok=True)
                with open(os.path.join(dest_dir, "duration.txt"), "w", encoding="utf-8") as f:
                    f.write(str(sources[source][destination]))
                faction_edges += 1
        total_edges += faction_edges
        print(f"{faction}: {len(sources)} sources, {faction_edges} edges")

    print(f"Total: {total_edges} directed edges")
    print(f"Wrote folder structure to {OUT_DIR}")


if __name__ == "__main__":
    main()
