#! /usr/bin/env python
import asyncio
import argparse
import sys
import time
from collections import defaultdict
from operator import attrgetter

import aiohttp
import colorama
import tqdm

from namescan import util
from namescan.platforms import Platforms

BAR_WIDTH = 50
BAR_FORMAT = "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed_s:.2f}s]"
TIMEOUT_PER_QUERY = 1
CLEAR_LINE = "\x1b[2K"
DIVIDER = "-"
DIVIDER_LENGTH = 40


async def main():
    startTime = time.time()
    colorama.init(autoreset=True)
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="Command-line interface for querying username availability on online platforms: " + ", ".join(p.name.capitalize() for p in Platforms))
    parser.add_argument("usernames", metavar="USERNAME", nargs="*",
                        help="one or more usernames to query")
    parser.add_argument("--restrict", "-r", metavar="PLATFORM", nargs="*", help="restrict list of platforms to query "
                                                                                "(default: all platforms)")
    parser.add_argument("--input-file", "-i", metavar="INPUTFILE.TXT",
                        help="file from which to read in usernames, one per line")
    parser.add_argument("--cache-tokens", "-c", action="store_true", help="cache tokens for platforms requiring more than one HTTP request (Snapchat, GitHub, Instagram & Tumblr) "
                        "marginally increases runtime but halves number of requests")
    parser.add_argument("--available-only", "-a", action="store_true", help="only print usernames that are available")
    args = parser.parse_args()

    usernames = args.usernames
    if args.input_file:
        with open(args.input, "r") as f:
            for line in f:
                usernames.append(line.strip("\n"))
    if not args.usernames:
        raise ValueError("you must specify either a username or an input file")
    if args.restrict:
        platforms = []
        for p in args.restrict:
            if p.upper() in Platforms.__members__:
                platforms.append(Platforms[p.upper()])
            else:
                raise ValueError(p + " is not a valid platform")
    else:
        platforms = [p for p in Platforms]
    usernames = list(dict.fromkeys(usernames))

    async with aiohttp.ClientSession() as session:
        if args.cache_tokens:
            print("Caching tokens...", end="")
            await asyncio.gather(*(util.prerequest(platform, session) for platform in platforms))
            print(CLEAR_LINE, end="")
        platform_queries = [util.is_username_available(i, username, session) for username in usernames for i in platforms]
        results = defaultdict(list)
        exceptions = []
        for future in tqdm.tqdm(asyncio.as_completed(platform_queries), total=len(platform_queries), leave=False, ncols=BAR_WIDTH, bar_format=BAR_FORMAT):
            try:
                response = await future
                if args.available_only and response.valid or not args.available_only:
                    results[response.username].append(response)
            # Catch only networking errors and errors in JSON handling
            except (aiohttp.ClientError, KeyError) as e:
                exceptions.append(colorama.Back.RED + f"{type(e).__name__}: {e}")
        for username in usernames:
            responses = results[username]
            print(DIVIDER * DIVIDER_LENGTH)
            print(" " * (DIVIDER_LENGTH // 2 - len(username) // 2) + colorama.Style.BRIGHT + username)
            print(DIVIDER * DIVIDER_LENGTH)
            responses.sort(key=attrgetter('platform.name'))
            responses.sort(key=attrgetter('valid', "success"), reverse=True)
            for response in responses:
                if not response.success:
                    name_col = colorama.Fore.WHITE
                    message_col = colorama.Fore.RED
                elif response.valid:
                    name_col = message_col = colorama.Fore.GREEN
                else:
                    name_col = colorama.Fore.WHITE
                    message_col = colorama.Fore.YELLOW
                print(name_col + f"{response.platform.name.capitalize()}", end="")
                print(name_col + ": " + message_col + f"{response.message}" if not response.valid else "")
    print(*exceptions, sep="\n", file=sys.stderr)
    print("Completed {} queries in {:.2f}s".format(len(platform_queries), time.time() - startTime))