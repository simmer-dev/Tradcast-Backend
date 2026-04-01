import random


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


def _generate_self_username() -> str:
    adj = random.choice(_ADJECTIVES)
    noun = random.choice(_NOUNS)
    suffix = random.randint(100, 9999)
    return f"{adj}{noun}{suffix}"
