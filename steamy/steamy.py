import re, xmltodict, time, logging, json, requests
from datetime import datetime
from pyquery import PyQuery

log = logging.getLogger(__name__)

MARKET_URL = u"http://steamcommunity.com/market/"
MARKET_SEARCH_URL = MARKET_URL + "search/render/{args}"
STEAM_GROUP_LIST_URL = u"http://steamcommunity.com/groups/{id}/memberslistxml/?xml=1"

LIST_ITEMS_QUERY = u"http://steamcommunity.com/market/search/render/?query={query}&start={start}&count={count}&search_descriptions=0&sort_column={sort}&sort_dir={order}&appid={appid}"
ITEM_PRICE_QUERY = u"http://steamcommunity.com/market/priceoverview/?country=US&currency=1&appid={appid}&market_hash_name={name}"
ITEM_PAGE_QUERY = u"http://steamcommunity.com/market/listings/{appid}/{name}"
INVENTORY_QUERY = u"http://steamcommunity.com/profiles/{id}/inventory/json/{app}/{ctx}"
BULK_ITEM_PRICE_QUERY = u"http://steamcommunity.com/market/itemordershistogram?country=US&language=english&currency=1&item_nameid={nameid}"

steam_id_re = re.compile('steamcommunity.com/openid/id/(.*?)$')
class_id_re = re.compile('"classid":"(\\d+)"')
name_id_re = re.compile('Market_LoadOrderSpread\( (\\d+) \)\;')

def format_query_string(**kwargs):
    return "?" + '&'.join(['%s=%s' % i for i in kwargs.items()])

def retry_request(f, count=5, delay=3):
    for _ in range(count):
        try:
            r = f(requests)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException:
            log.exception("Failed to make a request in retry-mode: ")
            time.sleep(delay)
    return None

class WorkshopEntity(object):
    """
    Represents an entity on the Steam workshop. This is a base
    class that has some base attributes for workshop items, which
    is inherited by sub-types/objects
    """
    def __init__(self, id, title, desc, game, user):
        self.id = id
        self.title = title
        self.desc = desc
        self.game = game
        self.user = user
        self.tags = []

class WorkshopFile(WorkshopEntity):
    """
    Represents an actual file on the workshop. Normally a map,
    sometimes other types of files (skins, etc)
    """
    def __init__(self, *args):
        super(WorkshopFile, self).__init__(*args)

        self.size = None
        self.posted = None
        self.updated = None
        self.thumb = None
        self.images = []

class WorkshopCollection(WorkshopEntity):
    """
    Represents a collection of workshop files
    """
    def __init__(self, *args):
        super(WorkshopCollection, self).__init__(*args)

        self.files = []

class SteamAPIError(Exception):
    """
    This Exception is raised when the Steam API
    either times out, or returns invalid data to us
    """

class InvalidInventoryException(SteamAPIError):
    """
    This exception is raised when an inventory is empty or invalid. Generally
    this will be raised if the user does not own the game, or has never owned
    an item from the game. May also occur from invalid appid/contextid
    """

class SteamAPI(object):
    """
    A wrapper around the normal steam API
    """
    def __init__(self, key, retry=True):
        self.key = key
        self.retry = retry

    def market(self, appid):
        """
        Obtain a SteamMarketAPI object with a proper Steam API key set
        """
        return SteamMarketAPI(appid, key=self.key)

    def request(self, url, data, verb="GET", **kwargs):
        """
        A meta function used to call the steam API
        """
        url = "http://api.steampowered.com/%s" % url
        data['key'] = self.key

        if self.retry:
            resp = retry_request(lambda f: getattr(f, verb.lower())(url, params=data, **kwargs))
        else:
            resp = getattr(requests, verb.lower())(url, params=data, **kwargs)

        if not resp:
            raise SteamAPIError("Failed to request url `%s`" % url)
        return resp.json()

    def get_trade_offer(self, id):
        """
        Gets a TradeOffer object for the given id
        """
        data = self.request("IEconService/GetTradeOffer/v1/", {
            "tradeofferid": id
        }, timeout=10)

        return data["response"]["offer"]

    def cancel_trade_offer(self, id):
        data = self.request("IEconService/CancelTradeOffer/v1/", {
            "tradeofferid": id
        }, timeout=10, verb="POST")

        return True

    def get_friend_list(self, id, relationship="all"):
        data = self.request("ISteamUser/GetFriendList/v0001/", {
            "steamid": id,
            "relationship": relationship
        }, timeout=10)

        return map(lambda i: i.get("steamid"), data["friendslist"]["friends"])

    def get_from_vanity(self, vanity):
        """
        Returns a steamid from a vanity name
        """

        data = self.rqeuest("ISteamUser/ResolveVanityURL/v0001/", {
            "vanityurl": vanity
        }, timeout=10)

        return int(data["response"].get("steamid", 0))

    def get_group_members(self, id, page=1):
        """
        Returns a list of steam 64bit ID's for every member in group `group`,
        a group public shortname or ID.
        """
        r = retry_request(lambda f: f.get(STEAM_GROUP_LIST_URL.format(id=id), timeout=10, params={
            "p": page
        }))

        if not r:
            raise SteamAPIError("Failed to getGroupMembers for group id `%s`" % id)

        try:
            data = xmltodict.parse(r.content)
        except Exception:
            raise SteamAPIError("Failed to parse result from getGroupMembers for group id `%s`" % id)

        return map(int, data['memberList']['members'].values()[0])

    def get_user_info(self, id):
        """
        Returns a dictionary of user info for a steam id
        """

        data = self.request("ISteamUser/GetPlayerSummaries/v0001", {
            "steamids": id
        }, timeout=10)

        if not data['response']['players']['player'][0]:
            raise SteamAPIError("Failed to get user info for user id `%s`" % id)

        return data['response']['players']['player'][0]

    def get_recent_games(self, id):
        return self.request("IPlayerService/GetRecentlyPlayedGames/v0001", {"steamid": id}, timeout=10)["response"]["games"]

    def get_player_bans(self, id):
        data = self.request("ISteamUser/GetPlayerBans/v1", {
            "steamids": str(id)
        }, timeout=10)

        return data["players"][0]

    def get_workshop_file(self, id):
        r = retry_request(lambda f: f.get("http://steamcommunity.com/sharedfiles/filedetails/", params={"id": id}, timeout=10))
        q = PyQuery(r.content)

        if not len(q(".breadcrumbs")):
            raise SteamAPIError("Failed to get workshop file id `%s`" % id)

        breadcrumbs = [(i.text, i.get("href")) for i in q(".breadcrumbs")[0]]
        if not len(breadcrumbs):
            raise Exception("Invalid Workshop ID!")

        gameid = int(breadcrumbs[0][1].rsplit("/", 1)[-1])
        userid = re.findall("steamcommunity.com/(profiles|id)/(.*?)$",
            breadcrumbs[-1][1])[0][-1].split("/", 1)[0]
        title = q(".workshopItemTitle")[0].text

        desc = (q(".workshopItemDescription") if len(q(".workshopItemDescription"))
            else q(".workshopItemDescriptionForCollection"))[0].text

        if len(breadcrumbs) == 3:
            size, posted, updated = [[x.text for x in i]
                for i in q(".detailsStatsContainerRight")][0]

            wf = WorkshopFile(id, title, desc, gameid, userid)
            wf.size = size
            wf.posted = posted
            wf.updated = updated
            wf.tags = [i[1].text.lower() for i in q(".workshopTags")]
            thumbs = q(".highlight_strip_screenshot")
            base = q(".workshopItemPreviewImageEnlargeable")
            if len(thumbs):
                wf.images = [i[0].get("src").rsplit("/", 1)[0]+"/" for i in thumbs]
            elif len(base):
                wf.images.append(base[0].get("src").rsplit("/", 1)[0]+"/")
            if len(q(".workshopItemPreviewImageMain")):
                wf.thumb = q(".workshopItemPreviewImageMain")[0].get("src")
            else:
                wf.thumb = wf.images[0]

            return wf
        elif len(breadcrumbs) == 4 and breadcrumbs[2][0] == "Collections":
            wc = WorkshopCollection(id, title, desc, gameid, userid)
            for item in q(".workshopItem"):
                id = item[0].get("href").rsplit("?id=", 1)[-1]
                wc.files.append(self.getWorkshopFile(id))
            return wc

    def get_asset_class_info(self, assetid, appid, instanceid=None):
        args = {
            "appid": appid,
            "class_count": 1,
            "classid0": assetid
        }

        ikey = str(assetid)
        if instanceid:
            args['instanceid0'] = instaceid
            ikey = "{}_{}".format(assetid, instanceid)

        data = self.request("ISteamEconomy/GetAssetClassInfo/v001/", args, timeout=10)
        return data["result"][ikey]

class SteamMarketAPI(object):
    def __init__(self, appid, key=None, retries=5):
        self.appid = appid
        self.key = key
        self.retries = retries

    def get_inventory(self, steamid, context=2):
        url = INVENTORY_QUERY.format(id=steamid, app=self.appid, ctx=context)

        r = retry_request(lambda f: f.get(url, timeout=10))
        if not r:
            raise SteamAPIError("Failed to get inventory for steamid %s" % id)

        data = r.json()
        if not data.get("success"):
            raise InvalidInventoryException("Invalid Inventory")

        return data

    def parse_item_name(self, name):
        # Strip out unicode
        name = filter(lambda i: ord(i) <= 256, name)

        r_skin = ""
        r_wear = ""
        r_stat = False
        r_holo = False
        r_mkit = False
        parsed = False

        if name.strip().startswith("Sticker"):
            r_item = "sticker"
            r_skin = name.split("|", 1)[-1]
            if "(holo)" in r_skin:
                r_skin = r_skin.replace("(holo)")
                r_holo = True
            if "|" in r_skin:
                r_skin, r_wear = r_skin.split("|", 1)
            parsed = True
        elif name.strip().startswith("Music Kit"):
            r_item = "musickit"
            r_skin = name.split("|", 1)[-1]
            r_mkit = True
        else:
            if '|' in name:
                start, end = name.split(" | ")
            else:
                start = name
                end = None

            if start.strip().startswith("StatTrak"):
                r_stat = True
                r_item = start.split(" ", 2)[-1]
            else:
                r_stat = False
                r_item = start.strip()

            if end:
                r_skin, ext = end.split("(")
                r_wear = ext.replace(")", "")
            parsed = True

        if not parsed:
            log.warning("Failed to parse item name `%s`" % name)

        return (
            r_item.lower().strip() or None,
            r_skin.lower().strip() or None,
            r_wear.lower().strip() or None,
            r_stat,
            r_holo,
            r_mkit
        )

    def get_item_count(self, query=""):
        r = retry_request(lambda f: f.get(MARKET_SEARCH_URL.format(args=format_query_string(
            query=query, appid=self.appid
        ))))

        if not r:
            raise SteamAPIError("Failed to get item count for query `%s`" % query)

        return r.json()["total_count"]

    def list_items(self, query="", start=0, count=10, sort="quantity", order="desc"):
        url = LIST_ITEMS_QUERY.format(
            query=query,
            start=start,
            count=count,
            sort=sort,
            order=order,
            appid=self.appid)

        r = retry_request(lambda f: f.get(url))
        if not r:
            log.error("Failed to list items: %s", url)
            return None

        pq = PyQuery(r.json()["results_html"])
        rows = pq(".market_listing_row .market_listing_item_name")
        return map(lambda i: i.text, rows)

    def get_item_meta(self, item_name):
        r = retry_request(
            lambda f: f.get(ITEM_PAGE_QUERY.format(name=item_name, appid=self.appid), timeout=10))

        if not r:
            raise SteamAPIError("Failed to get item meta data for item `%s`" % item_name)

        data = {}

        class_id = class_id_re.findall(r.content)
        if not len(class_id):
            raise SteamAPIError("Failed to find class_id for item_meta `%s`" % item_name)
        data["classid"] = int(class_id[0])

        name_id = name_id_re.findall(r.content)
        data["nameid"] = name_id[0] if len(name_id) else None

        pq = PyQuery(r.content)
        try:
            data["image"] = pq(".market_listing_largeimage")[0][0].get("src")
        except Exception:
            data["image"] = None

        return data

    def get_bulkitem_price(self, nameid):
        url = BULK_ITEM_PRICE_QUERY.format(nameid=nameid)
        r = retry_request(lambda f: f.get(url))

        if not r:
            raise SteamAPIError("Failed to get bulkitem price for nameid `%s`" % nameid)
        r = r.json()

        data = PyQuery(r["sell_order_summary"])("span")
        b_volume = int(data.text().split(" ", 1)[0])
        b_price = int(r["lowest_sell_order"]) * .01

        return b_volume, b_price

    def get_historical_price_data(self, item_name):
        url = ITEM_PAGE_QUERY.format(name=item_name, appid=self.appid)
        r = retry_request(lambda f: f.get(url))
        if not r:
            raise Exception("Failed to get historical price data for `%s`" % item_name)

        if not "var line1=[[" in r.content:
            raise Exception("Invalid response from steam for historical price data")
        data = json.loads(r.content.split("var line1=", 1)[-1].split(";", 1)[0])
        return data

    def get_item_price_history(self, item_name):
        url = ITEM_PAGE_QUERY.format(
            name=item_name,
            appid=self.appid)

        r = retry_request(lambda f: f.get(url))
        if not r:
            raise SteamAPIError("Failed to get_item_price_history for item `%s`" % item_name)

        if 'var line1' not in r.content:
            raise SteamAPIError("Invalid response for get_item_price_history of `%s`" % item_name)

        raw = json.loads(re.findall("var line1=(.+);", r.content)[0])

        keys = map(lambda i: datetime.strptime(i[0].split(":")[0], "%b %d %Y %M"), raw)
        values = map(lambda i: i[1], raw)
        return dict(zip(keys, values))

    def get_item_price(self, item_name):
        url = ITEM_PRICE_QUERY.format(
            name=item_name,
            appid=self.appid)

        r = retry_request(lambda f: f.get(url))
        if not r:
            return (0, 0.0, 0.0)

        r = r.json()
        return (
            int(r["volume"].replace(",", "")) if 'volume' in r else -1,
            float(r["lowest_price"].split(";")[-1]) if 'lowest_price' in r else 0.0,
            float(r["median_price"].split(";")[-1]) if 'median_price' in r else 0.0,
        )

