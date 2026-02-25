# -*- coding: utf-8 -*-

__doc__ = """
Access your GitHub repos quickly through Albert.

This plugin caches all repos for a list of accounts (configured via the
plugin settings).

It then allows opening the repo home page, PRs or issues.
"""


md_iid = "5.0"
md_version = "2.0"
md_name = "GitHub projects"
md_description = "Open your GitHub projects using Albert"
md_license = "MIT"
md_url = "https://github.com/symroe/albert_github"
md_maintainers = ["https://mastodon.me.uk/@symroe"]
md_lib_dependencies = ["requests"]

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import requests
from albert import *

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.expanduser("~/.cache/albert/github_plugin.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


@dataclass
class Repo:
    account: str
    name: str
    url: str
    description: str

    def to_dict(self):
        return self.__dict__

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def matches_query(self, query):
        return query in self.name.lower()


class GitHubHelper:
    def __init__(self, accounts, cache_path):
        self.accounts = accounts
        self.cache_path = Path(cache_path) / "gh_cache.json"
        self.cache = []
        logger.info(f"Initializing GitHubHelper with accounts: '{accounts}'")
        logger.info(f"Cache path: {self.cache_path}")

        if os.path.exists(self.cache_path):
            try:
                cached_data = json.load(open(self.cache_path))
                self.cache = [
                    Repo.from_dict(cached_repo) for cached_repo in cached_data
                ]
                logger.info(f"Loaded {len(self.cache)} repos from cache")
            except Exception as e:
                logger.error(f"Failed to load cache: {e}")
        else:
            logger.warning(f"Cache file does not exist at {self.cache_path}")

    def get_accounts(self):
        """
        Gets the accounts string from the config and returns a list of them

        :return: list of accounts
        """
        accounts = []
        for account in self.accounts.split(","):
            if account.strip():
                accounts.append(account.strip())
        logger.info(f"Parsed accounts: {accounts}")
        return accounts

    def get_repos_for_account(self, account):
        repos = []
        url = "https://api.github.com/search/repositories?q=user:{}".format(
            account.lower()
        )
        logger.info(f"Fetching repos for account: {account}")
        logger.debug(f"Initial URL: {url}")

        page_count = 0
        while url:
            try:
                page_count += 1
                logger.debug(f"Fetching page {page_count}: {url}")
                req = requests.get(url, timeout=10)

                logger.debug(f"Response status: {req.status_code}")
                logger.debug(
                    f"Rate limit remaining: {req.headers.get('X-RateLimit-Remaining')}"
                )

                if req.status_code != 200:
                    logger.error(
                        f"API request failed with status {req.status_code}: {req.text}"
                    )
                    break

                data = req.json()

                if "items" not in data:
                    logger.error(
                        f"No 'items' in response. Keys: {data.keys()}. Message: {data.get('message', 'N/A')}"
                    )
                    break

                logger.info(f"Found {len(data['items'])} repos in page {page_count}")
                url = req.links.get("next", {}).get("url")

                for repo in data["items"]:
                    if repo["archived"] == True:
                        logger.debug(f"Skipping archived repo: {repo['name']}")
                        continue
                    repos.append(
                        Repo(
                            name=repo["name"],
                            account=repo["owner"]["login"],
                            url=repo["html_url"],
                            description=repo["description"] or "",
                        )
                    )
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed for {url}: {e}")
                break
            except Exception as e:
                logger.error(
                    f"Error processing repos for account {account}: {e}", exc_info=True
                )
                break

        logger.info(f"Total repos fetched for {account}: {len(repos)}")
        return repos

    def cache_all_repos(self, overwrite=True):
        logger.info(f"cache_all_repos called with overwrite={overwrite}")
        if not overwrite and self.cache_path.exists():
            logger.info("Cache exists and overwrite=False, skipping refresh")
            return

        repos = []
        accounts = self.get_accounts()

        if not accounts or (len(accounts) == 1 and not accounts[0]):
            logger.warning("No accounts configured!")
            return

        logger.info(f"Fetching repos for {len(accounts)} account(s)")
        for account in accounts:
            account_repos = self.get_repos_for_account(account)
            repos += account_repos
            logger.info(f"Account {account}: fetched {len(account_repos)} repos")

        logger.info(f"Total repos to cache: {len(repos)}")

        try:
            # Ensure the cache directory exists
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured cache directory exists: {self.cache_path.parent}")

            with open(self.cache_path, "w") as f:
                f.write(json.dumps([repo.to_dict() for repo in repos], indent=4))
            self.cache = repos
            logger.info(f"Successfully cached {len(repos)} repos to {self.cache_path}")
        except Exception as e:
            logger.error(f"Failed to write cache: {e}", exc_info=True)


class Plugin(PluginInstance, GeneratorQueryHandler):
    executables = []

    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)
        logger.info("Plugin initializing...")

        self._accounts = self.readConfig("accounts", str)
        logger.info(f"Read accounts from config: '{self._accounts}'")

        if self._accounts is None:
            self._accounts = ""
            logger.warning("No accounts configured in settings")

        cache_location = self.cacheLocation()
        logger.info(f"Cache location: {cache_location}")
        self.gh = GitHubHelper(self.accounts, cache_location)

        # If cache is empty, try to populate it
        if not self.gh.cache:
            logger.info("Cache is empty, attempting initial population")
            self.gh.cache_all_repos(overwrite=False)

    def defaultTrigger(self):
        return "gh "

    def synopsis(self, query):
        return "repo name"

    @property
    def accounts(self):
        return self._accounts

    @accounts.setter
    def accounts(self, value):
        self._accounts = value
        self.writeConfig("accounts", value)
        self.gh.cache_all_repos()

    def configWidget(self):
        return [
            {
                "type": "lineedit",
                "property": "accounts",
                "label": "GitHub account or Organisations to index",
            }
        ]

    def items(self, context: QueryContext):
        logger.debug(f"Query triggered with string: '{context.query}'")
        logger.debug(f"Cache contains {len(self.gh.cache)} repos")

        if context.query.startswith("a "):
            # This is an admin command
            yield [
                StandardItem(
                    id="refresh",
                    text="Refresh",
                    subtext="Update cached repos from GitHub API",
                    icon_factory=lambda: Icon.theme("view-refresh"),
                    actions=[
                        Action(
                            id="update", text="Update", callable=self.gh.cache_all_repos
                        )
                    ],
                )
            ]
        else:
            matching_repos = [
                repo
                for repo in self.gh.cache
                if repo.matches_query(context.query.lower())
            ]
            logger.debug(f"Found {len(matching_repos)} matching repos")
            yield [self._make_item(repo, context) for repo in matching_repos]

    def _make_item(self, repo: Repo, context: QueryContext) -> Item:
        return StandardItem(
            id=f"{repo.account}-{repo.name}",
            text=repo.name,
            subtext=repo.description,
            input_action_text=context.trigger + repo.name,
            icon_factory=lambda: Icon.theme("github"),
            actions=[
                Action(
                    id="open",
                    text="Open repo on GitHub",
                    callable=lambda u=repo.url: openUrl(u),
                ),
                Action(
                    id="prs",
                    text="Open pull requests",
                    callable=lambda u=repo.url: openUrl(u + "/pulls"),
                ),
                Action(
                    id="issues",
                    text="Open issues",
                    callable=lambda u=repo.url: openUrl(u + "/issues"),
                ),
            ],
        )
