from google.cloud import firestore
from google.cloud.firestore_v1.async_client import AsyncClient
from datetime import datetime, timedelta, timezone
import string, asyncio, random
import time as _time
from typing import Optional, Dict, Any, List
from itertools import islice
from collections import defaultdict
from threading import Lock as _Lock
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from storage.create_username import *


class _ReadCounter:
    """Thread-safe counter for Firestore read operations, with periodic logging."""

    def __init__(self):
        self._lock = _Lock()
        self._total = defaultdict(int)
        self._window = defaultdict(int)
        self._window_start = _time.time()

    def inc(self, func_name: str, count: int = 1):
        with self._lock:
            self._total[func_name] += count
            self._window[func_name] += count

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "total": dict(sorted(self._total.items(), key=lambda x: x[1], reverse=True)),
                "total_sum": sum(self._total.values()),
                "window": dict(sorted(self._window.items(), key=lambda x: x[1], reverse=True)),
                "window_sum": sum(self._window.values()),
                "window_seconds": round(_time.time() - self._window_start, 1),
            }

    def flush_window(self) -> dict:
        with self._lock:
            snap = {
                "window": dict(sorted(self._window.items(), key=lambda x: x[1], reverse=True)),
                "window_sum": sum(self._window.values()),
                "window_seconds": round(_time.time() - self._window_start, 1),
                "total_sum": sum(self._total.values()),
            }
            self._window.clear()
            self._window_start = _time.time()
            return snap


_read_counter = _ReadCounter()
_INCR_TYPE = type(firestore.Increment(1))


class _TTLCache:
    """Simple in-memory cache with per-key TTL (seconds)."""

    def __init__(self):
        self._store: Dict[str, tuple] = {}

    def get(self, key: str, ttl: float):
        entry = self._store.get(key)
        if entry is not None:
            value, ts = entry
            if _time.monotonic() - ts < ttl:
                return value
            del self._store[key]
        return None

    def set(self, key: str, value):
        self._store[key] = (value, _time.monotonic())

    def clear(self):
        self._store.clear()


_ADJECTIVES = [
    # Nature & Weather
    "Arctic", "Amber", "Blazing", "Blizzard", "Cobalt", "Crimson", "Dusk", "Dawn",
    "Ember", "Frozen", "Glacial", "Golden", "Hazy", "Icy", "Jade", "Lunar",
    "Molten", "Misty", "Neon", "Onyx", "Opal", "Polar", "Radiant", "Ruby",
    "Solar", "Stormy", "Tidal", "Twilight", "Umbra", "Violet", "Volcanic", "Windy",
    "Foggy", "Cloudy", "Sunny", "Rainy", "Snowy", "Frosty", "Breezy", "Gloomy",
    "Scorching", "Humid", "Arid", "Dewy", "Murky", "Shimmering", "Glowing", "Gleaming",
    # Speed & Power
    "Turbo", "Hyper", "Ultra", "Warp", "Rapid", "Swift", "Rocket", "Surge",
    "Sonic", "Kinetic", "Charged", "Driven", "Fierce", "Furious", "Wild", "Savage",
    "Raging", "Relentless", "Ruthless", "Unstoppable", "Vicious", "Intense", "Raw", "Blunt",
    "Crashing", "Crushing", "Smashing", "Thundering", "Booming", "Roaring", "Howling", "Screaming",
    # Space & Sci-Fi
    "Astral", "Cosmic", "Galactic", "Interstellar", "Nebular", "Orbital", "Quantum", "Stellar",
    "Xenon", "Zeroth", "Zenith", "Photonic", "Plasmic", "Protonic", "Pulsing", "Binary",
    "Cyber", "Digital", "Electric", "Flux", "Infrared", "Laser", "Mach", "Atomic",
    "Nuclear", "Ionic", "Magnetic", "Graviton", "Tachyon", "Neutrino", "Darkmatter", "Hypersonic",
    "Subatomic", "Quantum", "Warped", "Dimensional", "Parallel", "Temporal", "Spatial", "Vortex",
    # Personality & Vibe
    "Bold", "Brave", "Calm", "Cunning", "Daring", "Dark", "Eager", "Elite",
    "Fair", "Faint", "Glad", "Grand", "Grim", "Heavy", "Heroic", "Iconic",
    "Iron", "Jagged", "Jolly", "Keen", "Kind", "Limitless", "Loud", "Magic",
    "Mild", "Mystic", "Noble", "Odd", "Prime", "Proud", "Quick", "Rare",
    "Rogue", "Royal", "Safe", "Stealth", "Tall", "Toxic", "Vast", "Vivid",
    "Warm", "Wicked", "Wired", "Zany", "Crisp", "Dusty", "Smooth", "Rough",
    "Sharp", "Slick", "Sleek", "Sly", "Smug", "Snappy", "Sneaky", "Solid",
    # Colors & Aesthetics
    "Scarlet", "Teal", "Indigo", "Cerulean", "Magenta", "Turquoise", "Ivory", "Obsidian",
    "Charcoal", "Platinum", "Bronze", "Silver", "Copper", "Titanium", "Sapphire", "Emerald",
    "Vermillion", "Maroon", "Burgundy", "Lavender", "Lilac", "Fuchsia", "Tangerine", "Chartreuse",
    "Alabaster", "Ochre", "Sepia", "Taupe", "Sienna", "Coral", "Peach", "Mauve",
    # Dark & Ominous
    "Ancient", "Broken", "Cursed", "Divine", "Eternal", "Fallen", "Gilded", "Hidden",
    "Infinite", "Legendary", "Nether", "Obscure", "Primal", "Risen", "Shadow", "Twisted",
    "Unholy", "Vengeful", "Abyssal", "Blighted", "Cryptic", "Doomed", "Eldritch", "Forsaken",
    "Haunted", "Infernal", "Jinxed", "Kaotic", "Lost", "Malevolent", "Nihil", "Ominous",
    "Plagued", "Ruined", "Sinister", "Tainted", "Undying", "Void", "Withered", "Xenith",
    "Yielded", "Zealous", "Accursed", "Banished", "Condemned", "Decrepit", "Exiled", "Forsaken",
    # Heroic & Epic
    "Almighty", "Celestial", "Dauntless", "Exalted", "Fearless", "Glorious", "Hallowed", "Immortal",
    "Just", "Knightly", "Luminous", "Majestic", "Omnipotent", "Pious", "Righteous", "Sacred",
    "Triumphant", "Unbroken", "Valiant", "Worthy", "Exalted", "Blessed", "Chosen", "Destined",
    "Fabled", "Honored", "Invincible", "Mighty", "Pure", "Revered", "Sovereign", "Undefeated",
    # Misc
    "Extreme", "Feral", "Ghost", "Infra", "Karma", "Lethal", "Mythic", "Omega",
    "Pixel", "Sigma", "Umber", "Venom", "Warped", "Xenith", "Phantom", "Spectral",
    "Shattered", "Fractured", "Distorted", "Corrupted", "Amplified", "Accelerated", "Augmented", "Enhanced",
    "Modified", "Overclocked", "Rebooted", "Restored", "Upgraded", "Evolved", "Mutated", "Transformed",
    "Aberrant", "Anomalous", "Chaotic", "Deviant", "Erratic", "Frantic", "Glitched", "Hectic",
    "Impure", "Jarring", "Kinetic", "Lurking", "Manic", "Nomadic", "Oblique", "Prowling",
]

_NOUNS = [
    # Animals
    "Falcon", "Tiger", "Panda", "Shark", "Eagle", "Viper", "Raven", "Wolf",
    "Hawk", "Bear", "Lion", "Lynx", "Cobra", "Drake", "Fox", "Panther",
    "Jaguar", "Leopard", "Cheetah", "Rhino", "Bison", "Condor", "Mamba", "Mantis",
    "Scorpion", "Hornet", "Barracuda", "Piranha", "Wolverine", "Badger", "Puma", "Coyote",
    "Stallion", "Mustang", "Bronco", "Pegasus", "Narwhal", "Walrus", "Moose", "Caribou",
    "Pelican", "Albatross", "Osprey", "Kestrel", "Merlin", "Harrier", "Buzzard", "Vulture",
    "Anaconda", "Python", "Moccasin", "Rattler", "Copperhead", "Sidewinder", "Taipan", "Krait",
    "Tarantula", "Widow", "Hornet", "Wasp", "Beetle", "Locust", "Cicada", "Cricket",
    # Mythology & Fantasy
    "Phoenix", "Dragon", "Kraken", "Hydra", "Wyvern", "Golem", "Specter", "Wraith",
    "Banshee", "Chimera", "Griffon", "Basilisk", "Leviathan", "Minotaur", "Cyclops", "Titan",
    "Daemon", "Djinn", "Valkyrie", "Siren", "Centaur", "Harpy", "Lich", "Revenant",
    "Selkie", "Kelpie", "Nymph", "Satyr", "Faun", "Dryad", "Naiad", "Nereid",
    "Colossus", "Behemoth", "Juggernaut", "Abomination", "Aberration", "Monstrosity", "Fiend", "Specter",
    "Shade", "Doppelganger", "Changeling", "Elemental", "Familiar", "Homunculus", "Imp", "Incubus",
    "Succubus", "Poltergeist", "Apparition", "Phantom", "Ghoul", "Zombie", "Vampire", "Werewolf",
    # Space & Cosmos
    "Nebula", "Pulsar", "Quasar", "Meteor", "Comet", "Orbit", "Nova", "Galaxy",
    "Photon", "Proton", "Neutron", "Reactor", "Supernova", "Void", "Cosmos", "Singularity",
    "Eclipse", "Solstice", "Equinox", "Zenith", "Nadir", "Apogee", "Perigee", "Meridian",
    "Magnetar", "Blazar", "Wormhole", "Stargate", "Dyson", "Horizon", "Parallax", "Perihelion",
    "Aphelion", "Syzygy", "Occultation", "Transit", "Conjunction", "Opposition", "Quadrature", "Elongation",
    "Cluster", "Filament", "Supercluster", "Void", "Bulge", "Halo", "Disk", "Arm",
    # Tech & Cyber
    "Pixel", "Byte", "Cache", "Token", "Block", "Node", "Stack", "Queue",
    "Vector", "Matrix", "Vertex", "Kernel", "Socket", "Cipher", "Shard", "Glitch",
    "Nexus", "Protocol", "Algorithm", "Syntax", "Binary", "Proxy", "Codec", "Firewall",
    "Payload", "Exploit", "Patch", "Script", "Module", "Runtime", "Compiler", "Debugger",
    "Thread", "Process", "Instance", "Container", "Pipeline", "Cluster", "Registry", "Daemon",
    "Endpoint", "Webhook", "Gateway", "Router", "Switch", "Bridge", "Relay", "Beacon",
    "Keystore", "Hashmap", "Iterator", "Pointer", "Buffer", "Frame", "Packet", "Signal",
    "Interrupt", "Mutex", "Semaphore", "Deadlock", "Bottleneck", "Latency", "Bandwidth", "Throughput",
    # Greek & Phonetic Alphabets
    "Sigma", "Delta", "Gamma", "Alpha", "Beta", "Omega", "Zeta", "Theta",
    "Lambda", "Epsilon", "Kappa", "Rho", "Tau", "Phi", "Chi", "Psi",
    "Iota", "Eta", "Nu", "Xi", "Omicron", "Upsilon", "Mu", "Pi",
    "Foxtrot", "Tango", "Yankee", "Victor", "Whiskey", "Romeo", "Juliet", "Oscar",
    # Warriors & Roles
    "Ranger", "Warden", "Stalker", "Seeker", "Hunter", "Raider", "Outlaw", "Nomad",
    "Drifter", "Pilgrim", "Scout", "Pilot", "Rogue", "Blade", "Vanguard", "Sentinel",
    "Guardian", "Champion", "Crusader", "Paladin", "Berserker", "Assassin", "Archer", "Duelist",
    "Mercenary", "Bounty", "Gladiator", "Legionnaire", "Centurion", "Praetor", "Lancer", "Pikeman",
    "Bowman", "Crossbow", "Slinger", "Cataphract", "Hussar", "Dragoon", "Cuirassier", "Grenadier",
    "Sniper", "Commando", "Operator", "Recon", "Infiltrator", "Saboteur", "Courier", "Handler",
    # Geography & Terrain
    "Abyss", "Bastion", "Citadel", "Crevice", "Dune", "Fjord", "Glacier", "Highland",
    "Island", "Jungle", "Lagoon", "Mesa", "Oasis", "Peak", "Ravine", "Summit",
    "Tundra", "Volcano", "Wasteland", "Canyon", "Cavern", "Estuary", "Gorge", "Plateau",
    "Steppe", "Taiga", "Savanna", "Badland", "Floodplain", "Peninsula", "Atoll", "Archipelago",
    "Massif", "Escarpment", "Butte", "Moor", "Fen", "Bog", "Marsh", "Swamp",
    "Tarn", "Mere", "Loch", "Fjord", "Inlet", "Sound", "Strait", "Channel",
    # Fire & Storm
    "Blaze", "Flame", "Ember", "Cinder", "Spark", "Flare", "Inferno", "Pyre",
    "Storm", "Thunder", "Lightning", "Tempest", "Cyclone", "Typhoon", "Gale", "Squall",
    "Maelstrom", "Vortex", "Whirlwind", "Dust Devil", "Firestorm", "Wildfire", "Backdraft", "Flashpoint",
    "Avalanche", "Landslide", "Mudslide", "Rockfall", "Sinkhole", "Tremor", "Aftershock", "Eruption",
    # Weapons & Gear
    "Blade", "Dagger", "Sword", "Saber", "Scythe", "Lance", "Spear", "Halberd",
    "Crossbow", "Longbow", "Quiver", "Gauntlet", "Buckler", "Bulwark", "Aegis", "Rampart",
    "Cannon", "Mortar", "Ballista", "Catapult", "Trebuchet", "Bombard", "Culverin", "Falconet",
    "Claymore", "Falchion", "Rapier", "Cutlass", "Dirk", "Stiletto", "Kukri", "Katar",
    # Misc Cool Nouns
    "Anvil", "Forge", "Vault", "Relic", "Totem", "Rune", "Glyph", "Sigil",
    "Torrent", "Cascade", "Tsunami", "Arrow", "Frost", "Stone", "Shadow", "Voyager",
    "Wreckage", "Remnant", "Fragment", "Echo", "Pulse", "Wave", "Surge", "Ripple",
    "Conduit", "Catalyst", "Prism", "Lens", "Mirror", "Crystal", "Shard", "Splinter",
    "Monument", "Monolith", "Obelisk", "Ziggurat", "Catacombs", "Labyrinth", "Sanctum", "Shrine",
]


def generate_self_username() -> str:
    adj = random.choice(_ADJECTIVES)
    noun = random.choice(_NOUNS)
    suffix = random.randint(100, 9999)
    return f"{adj}{noun}{suffix}"


class FirestoreManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    _ALLTIME_LB_TTL = 5

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.db: AsyncClient = firestore.AsyncClient(project="miniapp-479712", database='default-clone')
        self.users_collection = "users"
        self.trade_decisions_collection = "trade_decisions"
        self._keep_alive_started = False
        self._lb_cache = _TTLCache()
        self._users_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_only = False

    # ── cache helpers ──────────────────────────────────────────────

    async def load_all_users(self):
        """Bulk-load every user document into memory (called once on startup + daily sync)."""
        docs = await self.db.collection(self.users_collection).get()
        _read_counter.inc("load_all_users", len(docs))
        self._users_cache.clear()
        for doc in docs:
            self._users_cache[doc.id] = doc.to_dict()
        print(f"[CACHE] Loaded {len(self._users_cache)} users into memory")

    def _cache_apply(self, fid: str, updates: dict):
        """Apply Firestore-style updates (Increment / SERVER_TIMESTAMP) to the in-memory cache."""
        user = self._users_cache.get(fid)
        if user is None:
            return
        for k, v in updates.items():
            try:
                if v is SERVER_TIMESTAMP:
                    user[k] = datetime.now(timezone.utc)
                elif isinstance(v, _INCR_TYPE):
                    user[k] = user.get(k, 0) + v.value
                else:
                    user[k] = v
            except Exception as e:
                print(f"[CACHE] _cache_apply error  fid={fid} key={k}: {e}")

    # ── background loops ───────────────────────────────────────────

    async def start_keep_alive(self):
        if self._keep_alive_started:
            return
        self._keep_alive_started = True

        async def _ping_loop():
            while True:
                try:
                    await self.db.collection("_warmup").document("_ping").get()
                    _read_counter.inc("keep_alive_ping")
                except Exception as e:
                    print(f"Firestore keep-alive error: {e}")
                await asyncio.sleep(300)

        async def _reads_report_loop():
            while True:
                await asyncio.sleep(300)
                snap = _read_counter.flush_window()
                print(
                    f"[READS] last {snap['window_seconds']:.0f}s: "
                    f"{snap['window']}  "
                    f"window_total={snap['window_sum']}  "
                    f"all_time_total={snap['total_sum']}"
                )

        async def _daily_sync_loop():
            while True:
                now = datetime.now(timezone.utc)
                target = now.replace(hour=4, minute=0, second=0, microsecond=0)
                if now >= target:
                    target += timedelta(days=1)
                wait_secs = (target - now).total_seconds()
                print(f"[CACHE] Next daily sync in {wait_secs / 3600:.1f}h (04:00 UTC)")
                await asyncio.sleep(wait_secs)
                try:
                    await self.load_all_users()
                    print(f"[CACHE] Daily sync complete: {len(self._users_cache)} users")
                except Exception as e:
                    print(f"[CACHE] Daily sync error: {e}")

        asyncio.create_task(_ping_loop())
        asyncio.create_task(_reads_report_loop())
        asyncio.create_task(_daily_sync_loop())

    # ── username / invitation key generators (cache-only) ──────────

    def _generate_invitation_key(self, length: int = 6) -> str:
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

    def _generate_username(self) -> str:
        return generate_self_username()

    def _is_username_unique(self, username) -> bool:
        for u in self._users_cache.values():
            if u.get("username") == username:
                return False
        return True

    def _is_invitation_key_unique(self, key: str) -> bool:
        for u in self._users_cache.values():
            if u.get("invitation_key") == key:
                return False
        return True

    def _generate_unique_invitation_key(self) -> str:
        while True:
            key = self._generate_invitation_key()
            if self._is_invitation_key_unique(key):
                return key

    def _generate_unique_username(self) -> str:
        while True:
            uname = self._generate_username()
            if self._is_username_unique(uname):
                return uname

    # ── user CRUD ──────────────────────────────────────────────────

    async def initiate_user(self, fid: str, username: str = "", wallet: str = "", is_banned=False) -> Dict[str, Any]:
        invitation_key = self._generate_unique_invitation_key()
        username = self._generate_unique_username()

        user_data = {
            "username": username,
            "wallet": wallet,
            "total_games": 0,
            "last_online": firestore.SERVER_TIMESTAMP,
            "daily_games": 0,
            "total_profit": 0,
            "total_PnL": 0,
            "energy": 10,
            "streak_days": 1,
            "invitation_key": invitation_key,
            "invited_key": "",
            "is_banned": is_banned
        }

        await self.db.collection(self.users_collection).document(fid).set(user_data)

        await self.db.collection("leaderboard_scores").document(fid).set(
            {"daily_score": 0, "weekly_score": 0, "monthly_score": 0, "username": username}
        )

        cache_data = dict(user_data)
        cache_data["last_online"] = datetime.now(timezone.utc)
        self._users_cache[fid] = cache_data

        return cache_data

    async def get_user(self, fid: str) -> Optional[Dict[str, Any]]:
        cached = self._users_cache.get(fid)
        if cached is not None:
            return dict(cached)

        doc = await self.db.collection(self.users_collection).document(fid).get()
        _read_counter.inc("get_user_cache_miss")
        if doc.exists:
            data = doc.to_dict()
            self._users_cache[fid] = data
            return dict(data)
        return None

    async def get_users_batch(self, fids: List[str]) -> Dict[str, Dict]:
        users = {}
        miss_fids = []
        for fid in fids:
            cached = self._users_cache.get(fid)
            if cached is not None:
                users[fid] = dict(cached)
            else:
                miss_fids.append(fid)

        if miss_fids:
            async def fetch(fid):
                doc = await self.db.collection(self.users_collection).document(fid).get()
                _read_counter.inc("get_users_batch_miss")
                if doc.exists:
                    data = doc.to_dict()
                    self._users_cache[fid] = data
                    users[fid] = dict(data)
                else:
                    users[fid] = None

            await asyncio.gather(*[fetch(f) for f in miss_fids])
        return users

    async def update_user(self, fid: str, updates: Dict[str, Any]) -> bool:
        try:
            self._cache_apply(fid, updates)
            doc_ref = self.db.collection(self.users_collection).document(fid)
            await doc_ref.update(updates)
            return True
        except Exception as e:
            print(f"Error updating user {fid}: {e}")
            return False

    async def reduce_energy(self, fid: str) -> bool:
        try:
            user = self._users_cache.get(fid)
            if user is None:
                doc = await self.db.collection(self.users_collection).document(fid).get()
                _read_counter.inc("reduce_energy_miss")
                if not doc.exists:
                    return False
                user = doc.to_dict()
                self._users_cache[fid] = user

            energy = user.get("energy", 0)
            if energy <= 0:
                return False

            user["energy"] = energy - 1
            if not self.cache_only:
                await self.db.collection(self.users_collection).document(fid).update(
                    {"energy": firestore.Increment(-1)}
                )
            return True

        except Exception as e:
            print(f"Error reducing energy for {fid}: {e}")
            return False

    async def reset_streak_days(self, fid: str) -> bool:
        return await self.update_user(fid, {"streak_days": 1})

    async def increment_streak_days(self, fid: str) -> bool:
        try:
            updates = {"streak_days": firestore.Increment(1)}
            self._cache_apply(fid, updates)
            doc_ref = self.db.collection(self.users_collection).document(fid)
            await doc_ref.update(updates)
            return True
        except Exception as e:
            print(f"Error incrementing streak days for {fid}: {e}")
            return False

    async def track_user(self, fid: str, wallet: str, location: str, daily_games: int) -> Optional[str]:
        try:
            track_data = {
                "fid": fid,
                "wallet": wallet,
                "timestamp": datetime.now(timezone.utc),
                "location": location,
                "daily_games": daily_games
            }
            _, doc_ref = await self.db.collection("user_tracks").add(track_data)
            return doc_ref.id
        except Exception as e:
            print(f"Error tracking user {fid}: {e}")
            return None

    async def reset_daily_games(self, fid: str) -> bool:
        return await self.update_user(fid, {"daily_games": 0})

    async def increment_daily_games(self, fid: str) -> bool:
        try:
            updates = {"daily_games": firestore.Increment(1)}
            self._cache_apply(fid, updates)
            doc_ref = self.db.collection(self.users_collection).document(fid)
            await doc_ref.update(updates)
            return True
        except Exception as e:
            print(f"Error incrementing daily games: {e}")
            return False

    async def handle_daily_games(self, fid: str) -> bool:
        now = datetime.now(timezone.utc)
        user = await self.get_user(fid)
        last_online = user.get('last_online')
        daily_games = user.get('daily_games')

        if not last_online or last_online is SERVER_TIMESTAMP:
            await self.reset_daily_games(fid)
            await self.make_last_online_now(fid)
            return daily_games

        last_date = last_online.date()
        today = now.date()

        if last_date == today:
            await self.increment_daily_games(fid)
            return daily_games
        else:
            await self.reset_daily_games(fid)
            return daily_games

    async def make_last_online_now(self, fid: str) -> bool:
        return await self.update_user(fid, {"last_online": firestore.SERVER_TIMESTAMP})

    async def add_total_game(self, fid: str) -> bool:
        try:
            updates = {"total_games": firestore.Increment(1)}
            self._cache_apply(fid, updates)
            doc_ref = self.db.collection(self.users_collection).document(fid)
            await doc_ref.update(updates)
            return True
        except Exception as e:
            print(f"Error incrementing total games for {fid}: {e}")
            return False

    async def add_game_session(
        self,
        fid: str,
        trade_env_id: str,
        actions: List[Dict[str, Any]]
    ) -> bool:
        try:
            trade_decisions_data = {
                "fid": fid,
                "trade_env_id": trade_env_id,
                "actions": actions,
                "created_at": firestore.SERVER_TIMESTAMP
            }
            await self.db.collection(self.trade_decisions_collection).document(trade_env_id).set(
                trade_decisions_data
            )
            return True
        except Exception as e:
            print(f"Error adding game session for {fid}: {e}")
            return False

    async def get_game_sessions(self, fid: str) -> Optional[List[str]]:
        try:
            query = self.db.collection(self.trade_decisions_collection).where("fid", "==", fid)
            docs = await query.get()
            _read_counter.inc("get_game_sessions", len(docs) if docs else 1)
            if docs:
                return [doc.id for doc in docs]
            return []
        except Exception as e:
            print(f"Error getting game sessions for {fid}: {e}")
            return None

    async def get_trade_decisions(self, trade_env_id: str) -> Optional[Dict[str, Any]]:
        doc_ref = self.db.collection(self.trade_decisions_collection).document(trade_env_id)
        doc = await doc_ref.get()
        _read_counter.inc("get_trade_decisions")
        if doc.exists:
            return doc.to_dict()
        return None

    async def delete_user(self, fid: str) -> bool:
        try:
            from storage.local_trades_db import trades_db
            trades_db.delete_by_fid(fid)
            self._users_cache.pop(fid, None)
            await self.db.collection(self.users_collection).document(fid).delete()
            return True
        except Exception as e:
            print(f"Error deleting user {fid}: {e}")
            return False

    async def delete_multiple_users(self, fids: List[str]) -> Dict[str, bool]:
        async def delete_single(fid: str) -> tuple:
            success = await self.delete_user(fid)
            return (fid, success)

        tasks = [delete_single(fid) for fid in fids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        result_dict = {}
        for result in results:
            if isinstance(result, Exception):
                continue
            fid, success = result
            result_dict[fid] = success
        return result_dict

    # ── game result + leaderboard writes ───────────────────────────

    async def save_game_session_result(
            self,
            fid: str,
            final_pnl: float,
            final_profit: float,
    ) -> bool:
        try:
            updates = {
                "total_games": firestore.Increment(1),
                "total_profit": firestore.Increment(final_profit),
                "total_PnL": firestore.Increment(final_pnl),
                "last_online": firestore.SERVER_TIMESTAMP,
            }
            self._cache_apply(fid, updates)

            user_ref = self.db.collection(self.users_collection).document(fid)
            await user_ref.update(updates)

            username = (self._users_cache.get(fid) or {}).get("username", "")
            lb_update = {
                "daily_score": firestore.Increment(final_profit),
                "weekly_score": firestore.Increment(final_profit),
                "monthly_score": firestore.Increment(final_profit),
            }
            if username:
                lb_update["username"] = username
            await self.db.collection("leaderboard_scores").document(fid).set(
                lb_update, merge=True,
            )
            return True
        except Exception as e:
            print(f"Error saving game session result for {fid}: {e}")
            return False

    # ── leaderboards (all from cache, zero Firestore reads) ────────

    def _refresh_alltime_leaderboard(self, top_n: int) -> Dict[str, Any]:
        """Sort the in-memory user cache by total_profit. No Firestore reads."""
        sorted_users = sorted(
            self._users_cache.items(),
            key=lambda x: x[1].get("total_profit", 0),
            reverse=True,
        )

        top_entries = []
        fid_to_rank: Dict[str, int] = {}
        for idx, (fid, data) in enumerate(sorted_users, start=1):
            fid_to_rank[fid] = idx
            if idx <= top_n:
                top_entries.append({
                    "fid": fid,
                    "username": data.get("username", "Unknown"),
                    "total_profit": data.get("total_profit", 0),
                    "rank": idx,
                })

        result = {"top_entries": top_entries, "fid_to_rank": fid_to_rank}
        self._lb_cache.set(f"alltime_{top_n}", result)
        return result

    async def get_leaderboard(self, fid: str, top_n: int = 10) -> List[Dict[str, Any]]:
        try:
            cache_key = f"alltime_{top_n}"
            cached = self._lb_cache.get(cache_key, self._ALLTIME_LB_TTL)
            if cached is None:
                cached = self._refresh_alltime_leaderboard(top_n)

            top_entries = cached["top_entries"]
            fid_to_rank = cached["fid_to_rank"]

            leaderboard = []
            user_in_top = False

            for entry in top_entries:
                is_user = entry["fid"] == fid
                if is_user:
                    user_in_top = True
                leaderboard.append({
                    "username": entry["username"],
                    "total_profit": entry["total_profit"],
                    "the_user": is_user,
                    "rank": entry["rank"],
                })

            if not user_in_top:
                user_data = self._users_cache.get(fid, {})
                leaderboard.append({
                    "username": user_data.get("username", "Unknown"),
                    "total_profit": user_data.get("total_profit", 0),
                    "the_user": True,
                    "rank": fid_to_rank.get(fid, len(fid_to_rank) + 1),
                })

            return leaderboard

        except Exception as e:
            print(f"Error getting leaderboard: {e}")
            return []

    def get_latest_trades(self, fid: str, number: int = 4) -> List[Dict[str, Any]]:
        from storage.local_trades_db import trades_db
        return trades_db.get_latest_trades(fid, limit=number)


firestore_manager = FirestoreManager()
firestore_read_counter = _read_counter
