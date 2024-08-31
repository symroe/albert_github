# -*- coding: utf-8 -*-

__doc__ = """
Access your GutHub repos quickly through Albert.

This plugin caches all repos for a list of accounts (configured via the 
plugin settings). 

It then allows opening the repo home page, PRs or issues.
"""


md_iid = "2.0"
md_version = "1.6"
md_name = "GitHub projects"
md_description = "Open your GitHub projects using Albert"
md_license = "MIT"
md_url = "https://github.com/symroe/albert_github"
md_maintainers = "https://mastodon.me.uk/@symroe"

import json
import os
from dataclasses import dataclass

import requests
from albert import *


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
        self.cache_path = cache_path
        self.cache_path = self.cache_path / "gh_cache.json"
        if os.path.exists(self.cache_path):
            cached_data = json.load(open(self.cache_path))
            self.cache = [Repo.from_dict(cached_repo) for cached_repo in cached_data]

    def get_accounts(self):
        """
        Gets the accounts string from the config and returns a list of them

        :return: list of accounts
        """
        accounts = []
        for account in self.accounts.split(","):
            accounts.append(account.strip())
        return accounts

    def get_repos_for_account(self, account):
        repos = []
        url = "https://api.github.com/search/repositories?q=user:{}".format(account.lower())
        while url:
            req = requests.get(url)
            data = req.json()
            url = req.links.get("next", {}).get("url")

            for repo in data["items"]:
                if repo["archived"] == True:
                    continue
                repos.append(
                    Repo(
                        name=repo["name"],
                        account=repo["owner"]["login"],
                        url=repo["html_url"],
                        description=repo["description"] or "",
                    )
                )
        return repos

    def cache_all_repos(self, overwrite=True):
        if not overwrite and self.cache_path.exitst():
            return
        repos = []
        for account in self.get_accounts():
            repos += self.get_repos_for_account(account)

        with open(self.cache_path, "w") as f:
            f.write(json.dumps([repo.to_dict() for repo in repos], indent=4))
            self.cache = repos


class Plugin(PluginInstance, TriggerQueryHandler):
    executables = []

    def __init__(self):
        TriggerQueryHandler.__init__(
            self,
            id=md_id,
            name=md_name,
            description=md_description,
            synopsis="repo name",
            defaultTrigger="gh ",
        )
        PluginInstance.__init__(self, extensions=[self])
        self._accounts = self.readConfig("accounts", str)
        if self._accounts is None:
            self._accounts = ""

        self.gh = GitHubHelper(self.accounts, self.cacheLocation)

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

    def handleTriggerQuery(self, query: Query):
        if query.string.startswith("a "):
            # This is an admin command
            query.add(
                StandardItem(
                    id="refresh",
                    text="Refresh",
                    subtext="Update cached repos from GitHub API",
                    actions=[Action("update", "Update", self.gh.cache_all_repos)],
                )
            )
        else:
            query.add(
                [
                    self._make_item(repo, query)
                    for repo in self.gh.cache
                    if repo.matches_query(query.string.lower())
                ]
            )

    def _make_item(self, repo: Repo, query: Query) -> Item:
        return StandardItem(
            id=f"{repo.account}-{repo.name}",
            text=repo.name,
            subtext=repo.description,
            inputActionText=query.trigger + repo.name,
            actions=[
                Action("open", "Open repo on GitHub", lambda u=repo.url: openUrl(u)),
                Action(
                    "prs",
                    "Open pull requests",
                    lambda u=repo.url: openUrl(u + "/pulls"),
                ),
                Action(
                    "issues", "Open issues", lambda u=repo.url: openUrl(u + "/issues")
                ),
            ],
        )
