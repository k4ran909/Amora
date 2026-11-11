"""User-facing strings (HTML parse mode). English only for now; i18n arrives in phase 7."""

WELCOME = (
    "👋 <b>Welcome to {app}!</b>\n\n"
    "Meet real people, with no catfish. Every profile photo is checked to make sure it shows a real face, "
    "and every profile is reviewed by our team before it goes live.\n\n"
    "<b>Before we start:</b>\n"
    "• You must be <b>18 or older</b>\n"
    "• Use real photos of <b>yourself</b>\n"
    "• Be respectful: harassment, scams and explicit content get you banned\n"
    "• We store your profile securely and you can delete it anytime"
)

RULES = (
    "📄 <b>Community rules</b>\n\n"
    "1. 18+ only. Accounts that appear underage are removed permanently.\n"
    "2. Your photos must show your own face clearly. No celebrities, cartoons or stolen photos.\n"
    "3. No nudity or sexual content in photos or bio.\n"
    "4. No links, phone numbers, @usernames or ads in your profile.\n"
    "5. No harassment, hate speech, scams or requests for money.\n"
    "6. Report anyone who breaks these rules. Our team reviews every report.\n\n"
    "🔒 <b>Privacy:</b> we keep only what's needed to run the service. Face data is used only to check "
    "that your photos show the same real person, and it's deleted with your account."
)

ASK_DOB = "🎂 <b>When's your birthday?</b>\nSend it as <code>DD/MM/YYYY</code>, e.g. <code>21/04/2001</code>.\n<i>Only your age is shown on your profile.</i>"
UNDERAGE = "🚫 Sorry, you must be at least 18 to use {app}. Your registration has been closed."
ASK_GENDER = "🙋 <b>I am…</b>"
ASK_SHOW_ME = "💘 <b>Who do you want to meet?</b>"
ASK_LOOKING_FOR = "🎯 <b>What are you looking for?</b>"
ASK_NAME = "✍️ <b>What's your first name?</b>\nThis is how you'll appear to others."
ASK_LOCATION = (
    "📍 <b>Where are you?</b>\n"
    "Tap <b>Share my location</b> for the best matches nearby, or just type your city.\n"
    "<i>We never show your exact location, only the distance.</i>"
)
ASK_BIO = (
    "📝 <b>Write a short bio</b> (10–500 characters)\n"
    "What do you love doing? What makes you laugh? What are you looking for?\n"
    "<i>No links, phone numbers or @usernames.</i>"
)
ASK_INTERESTS = "🏷 <b>Pick your interests</b> ({min}–{max}). Tap to select, then press Done."
PHOTO_CONSENT = (
    "📸 <b>Photos time!</b>\n\n"
    "To keep {app} free of fake profiles, we automatically check every photo:\n"
    "• your <b>main photo</b> must clearly show only <b>your face</b>\n"
    "• every extra photo must include <b>you</b> (we compare faces with your main photo)\n\n"
    "We store an encrypted face fingerprint only for this check, and it's deleted with your account."
)
CONSENT_WHY = (
    "Most fake and scam profiles use photos without a face, or someone else's photos. "
    "Checking faces means everyone you see on {app} is a real person who looks like their photos."
)
ASK_PHOTOS = (
    "Send your <b>main photo</b> now: a clear photo of your face, looking at the camera, just you.\n"
    "Then you can add up to {extra} more photos. You can send several at once."
)
PHOTO_CHECKING = "🔍 Checking photo…"
PHOTO_OK_MAIN = "✅ <b>Main photo accepted</b>: face detected.\nAdd more photos (up to {max} total), or press Done."
PHOTO_OK_EXTRA = "✅ <b>Photo {n} accepted</b>: same person as your main photo."
PHOTO_REJECTED = "❌ <b>Photo not accepted</b>\n{reason}"
PHOTO_ONLY = "Please send a <b>photo</b> (as a picture or an image file). When you're finished, press Done."
PREVIEW_HEADER = "👀 <b>This is how others will see you:</b>"
SUBMITTED = (
    "⏳ <b>Profile submitted!</b>\n\n"
    "Our team reviews every profile, usually within a few hours. You'll get a message here as soon as you're approved."
)
UNDER_REVIEW = "⏳ Your profile is <b>under review</b>. We'll message you here as soon as it's approved."
WELCOME_BACK = "👋 Welcome back, <b>{name}</b>!"
APPROVED = "🎉 <b>Your profile is approved!</b>\nYou're now visible to others. Browsing opens very soon, so stay tuned!"
REJECTED = "⚠️ <b>Your profile needs changes</b>\nReason: <i>{reason}</i>\n\nTap below to fix it and submit again."
BANNED = "🚫 Your account has been suspended for breaking the community rules."
COMING_SOON = "🚧 <b>{feature}</b> is coming in the next update. Your profile is ready for it!"
NEED_PROFILE = "Finish your profile first. Send /start to continue."
EDIT_WARNING = (
    "✏️ <b>Edit profile</b>\n\nEditing restarts your profile setup and hides your profile until our team "
    "approves it again. Continue?"
)
DELETE_WARNING = (
    "🗑 <b>Delete your account?</b>\n\nThis permanently removes your profile, photos, matches and messages. "
    "It cannot be undone."
)
DELETED = "Your account and all your data have been deleted. Send /start any time to come back. 👋"
HELP = (
    "🆘 <b>Help & Safety</b>\n\n"
    "/start: continue or open the main menu\n"
    "/cancel: stop what you're doing\n\n"
    "<b>Stay safe:</b>\n"
    "• Meet in public places and tell a friend where you're going\n"
    "• Never send money or crypto to someone you met here\n"
    "• Keep chats inside the bot until you trust the person\n"
    "• Report anyone suspicious from their profile or the chat"
)
EXPIRED_BUTTON = "This button has expired."
