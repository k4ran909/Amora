"""Fixed option lists shared by both platforms."""

GENDERS: dict[str, str] = {
    "man": "👨 Man",
    "woman": "👩 Woman",
    "nonbinary": "⚧ Non-binary",
}

SHOW_ME: dict[str, tuple[str, list[str]]] = {
    "men": ("👨 Men", ["man"]),
    "women": ("👩 Women", ["woman"]),
    "everyone": ("🌈 Everyone", ["man", "woman", "nonbinary"]),
}

LOOKING_FOR: dict[str, str] = {
    "relationship": "💍 Relationship",
    "dating": "☕ Casual dating",
    "friends": "👋 New friends",
    "unsure": "🤷 Not sure yet",
}

INTERESTS: dict[str, str] = {
    "gaming": "🎮 Gaming",
    "music": "🎵 Music",
    "travel": "✈️ Travel",
    "gym": "🏋️ Gym",
    "cooking": "🍳 Cooking",
    "books": "📚 Books",
    "movies": "🎬 Movies",
    "pets": "🐶 Pets",
    "tech": "💻 Tech",
    "sports": "⚽ Sports",
    "art": "🎨 Art",
    "photography": "📷 Photography",
    "dancing": "💃 Dancing",
    "hiking": "🥾 Hiking",
    "coffee": "☕ Coffee",
    "foodie": "🍕 Foodie",
    "anime": "🍥 Anime",
    "fashion": "👗 Fashion",
    "yoga": "🧘 Yoga",
    "cars": "🚗 Cars",
    "nature": "🌿 Nature",
    "parties": "🎉 Parties",
    "writing": "✍️ Writing",
    "startups": "🚀 Startups",
}


def show_me_label(genders: list[str]) -> str:
    for label, values in SHOW_ME.values():
        if sorted(values) == sorted(genders):
            return label
    return ", ".join(GENDERS.get(g, g) for g in genders)
