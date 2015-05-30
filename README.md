# Steamy
Steamy is a lightweight, limited-abstraction interface to both the [public Steam Web API](https://developer.valvesoftware.com/wiki/Steam_Web_API) and a custom Steam Market API.

## Public Steam Web API
To interface with the public Steam Web API, you must have a [Steam API Key](https://steamcommunity.com/dev/apikey). To get started, create an instance of the SteamAPI interface:

```
steam = SteamAPI(my_api_key)
```

### Examples

Get a trade offer
```
offer = steam.get_trade_offer(offer_id)
assert offer['tradeofferid'] == offer_id
```

Get members for a group
```
members = steam.get_group_members("testgroupplzignore", page=1)
assert len(members)
```

### Workshop Interface
The SteamAPI interface also provides the ability to query workshop items:

```
wfile = steam.get_workshop_file("447269341")
assert isinstance(wfile, WorkshopFile)
assert wfile.id == "447269341"
```

