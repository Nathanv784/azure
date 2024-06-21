import json
import logging
from promptflow.tracing import trace
from api.agents.researcher import researcher
from api.agents.writer import writer
from api.agents.editor import editor
from api.agents.designer import designer
from api.agents.product import product
from api.logging import log_output
from api.evaluate.evaluators import evaluate_article_in_background
from dotenv import load_dotenv
load_dotenv()

@trace
def get_research(request, instructions, feedback):
     
    research_result = researcher.research(
        request=request,
        instructions=instructions,
        feedback=feedback
    )
    print(json.dumps(research_result, indent=2))
    return research_result

@trace
def get_writer(request, feedback, instructions, research=[], products=[]):
    writer_reponse = writer.write(
        request=request, feedback=feedback, instructions=instructions, research=research, products=products
    )
    print(json.dumps(writer_reponse, indent=2))
    return writer_reponse

@trace
def get_editor(article, feedback):
     
    editor_task = editor.edit(article, feedback)
    
    # Ensure the editor response is in JSON format
    if isinstance(editor_task, str):
        try:
            editor_task_json = json.loads(editor_task)
        except json.JSONDecodeError:
            # If it is not valid JSON, format it as a JSON string
            editor_task_json = {
                "decision": "reject feedback",
                "researchFeedback": "No Feedback",
                "editorFeedback": editor_task
            }
        editor_task = json.dumps(editor_task_json)
    
    print(json.dumps(editor_task, indent=2))
    return editor_task


@trace
def get_designer(request, instructions, feedback):
    designer_task = designer.design(request, instructions, feedback)
    print(json.dumps(designer_task, indent=2))
    return designer_task

# TODO: delete, I dont think this is used...
@trace
def regenerate_process(editor_response, context, instructions, product_documenation):
    # Get feedback for research from writer
    researchFeedback = (
        editor_response["researchFeedback"]
        if "researchFeedback" in editor_response
        else "No Feedback"
    )

    # Get feedback from writer from editor
    editorFeedback = (
        editor_response["editorFeedback"]
        if "editorFeedback" in editor_response
        else "No Feedback"
    )
    # Regenerate with feedback loop
    research_result = get_research(context, instructions, researchFeedback)
    writer_reponse = get_writer(
        context, editorFeedback, instructions, research=research_result, products=product_documenation
    )
    editor_response = get_editor(
        writer_reponse["context"]["article"], writer_reponse["context"]["feedback"]
    )
    return editor_response

@trace
def write_article(request, instructions, evaluate=False):
     
     
    log_output("Article generation started for request: %s, instructions: %s", request, instructions)

    feedback = "No Feedback"

    yield ("message", "Starting research agent task...")
    log_output("Getting researcher task output...")
    research_result = get_research(request, instructions, feedback)
    yield ("researcher", research_result)
    # Retrieve product information relevant to the user's query
    log_output("Product information...")
    product_documenation = product.get_products(request)
    # product_documenation={"id": "cHJvZHVjdHMueGxzeDQ=", "title": "", "content": "Title: products.xlsx, and peace of mind. Be wild, be free, be cooked for with the CompactCook Camping Stove!\n\n", "url": "products.xlsx"}, {"id": "cHJvZHVjdHMueGxzeDM=", "title": "", "content": "Title: products.xlsx\tStep up your hiking game with HikeMate's TrailLite Daypack. Built for comfort and efficiency, this lightweight and durable backpack offers a spacious main compartment, multiple pockets, and organization-friendly features all in one sleek package. The adjustable shoulder straps and padded back panel ensure optimal comfort during those long exhilarating treks. Course through nature without worry as the daypack's water-resistant fabric protects your essentials from unexpected showers. Plus, never run dry with the integrated hydration system. And did we mention it comes in a plethora of colors and designs? So you can choose one that truly speaks to your outdoorsy soul! Keeping your visibility in mind, we've added reflective accents that light up in low-light conditions. Don't just carry a backpack, adorn a companion that takes you a step ahead in your adventures. Trust the TrailLite Daypack for a hassle-free, enjoyable hiking experience\n\t9\tSummitClimber Backpack\t120\tBackpacks\tHikeMate\tAdventure waits for no one! Introducing the HikeMate SummitClimber Backpack, your reliable partner for every exhilarating journey. With a generous 60-liter capacity and multiple compartments and pockets, packing is a breeze. Every feature points to comfort and convenience; the ergonomic design and adjustable hip belt ensure a pleasantly personalized fit, while padded shoulder straps protect you from the burden of carrying. Venturing into wet weather? Fear not! The integrated rain cover has your back, literally. Stay hydrated thanks to the backpack's hydration system compatibility. Travelling during twilight? Reflective accents keep you visible in low-light conditions. The SummitClimber Backpack isn't merely a carrier; it's a wearable base camp constructed from ruggedly durable nylon and thoughtfully designed for the great outdoors adventurer, promising to withstand tough conditions and provide years of service. So, set off on that quest - the wild beckons! The SummitClimber Backpack - your hearty companion on every expedition!"}
    yield ("products", product_documenation)
    # Then send it to the writer, the writer writes the article
    yield ("message", "Starting writer agent task...")
    log_output("Getting writer task output...")
    writer_response = get_writer(request, feedback, instructions, research=research_result, products=product_documenation)
    yield ("writer", writer_response)
    # Then send it to the editor, to decide if it's good or not
    yield ("message", "Starting editor agent task...")
    log_output("Getting editor task output...")
    editor_response = get_editor(writer_response["article"], writer_response["feedback"])
    log_output("Editor response: %s", editor_response)

    yield ("editor", editor_response)
    retry_count = 0

    print(f"Editor response raw: {editor_response}")

    try:
        editor_response_dict = json.loads(editor_response)
    except json.JSONDecodeError as e:
        log_output("Failed to parse editor response: %s", str(e))
        return

    while(str(editor_response_dict["decision"]).lower().startswith("accept")):
        yield ("message", f"Sending editor feedback ({retry_count + 1})...")
        log_output("Regeneration attempt %d based on editor feedback", retry_count + 1)

        researchFeedback = editor_response_dict.get("researchFeedback", "No Feedback")
        editorFeedback = editor_response_dict.get("editorFeedback", "No Feedback")
        
        research_result = get_research(request, instructions, researchFeedback)
        yield ("researcher", research_result)

        writer_response = get_writer(request, editorFeedback, instructions, research=research_result, products=product_documenation)
        yield ("writer", writer_response)

        editor_response = get_editor(writer_response["article"], writer_response["feedback"])
        try:
            editor_response_dict = json.loads(editor_response)
        except json.JSONDecodeError as e:
            log_output("Failed to parse editor response during loop: %s", str(e))
            break
        yield ("editor", editor_response)

        retry_count += 1
        if retry_count >= 2:
            break

    log_output("Editor accepted article after %d iterations", retry_count)
    yield ("message", "Editor accepted article")

    # writer_response="**Unlock the Great Outdoors: Gear Up for Unforgettable Adventures**\n\nHello, adventurers and nature enthusiasts! Whether you're plotting your next expedition to the world's best cities or escaping to the serene tranquility of nature, gearing up with the right equipment can transform your outdoor experience from mundane to extraordinary. From the bustling streets of New York, the charming vistas of Lisbon, to the captivating allure of Paris, every journey begins with a single step\u2014and the perfect gear.\n\nMeet the **CompactCook Camping Stove** and **EcoFire's Camping Stove**, your new best friends for outdoor culinary adventures. These aren't just stoves; they're your passport to the wilderness, offering the peace of mind that comes with knowing a hot, delicious meal is just moments away. Designed to withstand the elements, they're compact, lightweight, and incredibly easy to pack, ensuring you're well-fed whether you're high in the mountains or deep in the forest.\n\nBut what's an adventure without the right pack to carry your essentials? Enter the **HikeMate's TrailLite Daypack** and **SummitClimber Backpack**. These aren't just bags; they're your trusty sidekicks ready to store all your treasures while ensuring ultimate comfort and convenience. With spacious compartments, water-resistant fabric, and integrated hydration systems, they are the perfect companions for day hikes or longer treks. Plus, with reflective accents for visibility, these backpacks ensure you're safe and seen, from dawn till dusk.\n\nLet's talk comfort. The **RainGuard Hiking Jacket** is your shield against the unpredictable whims of nature, keeping you dry and comfortable in the face of rain and wind. And when it comes to the terrain, the **TrekStar Hiking Sandals** and **TrailWalker Hiking Shoes** ensure every step is secure and comfortable, blending durability with breathability for your trekking endeavors.\n\nNow, where to rest after a day of adventure? The **Alpine Explorer Tent** offers a cozy retreat that feels like a second home under the stars, while the **CozyNights Sleeping Bag** wraps you in warmth and comfort, ensuring a restful sleep amidst the soothing sounds of nature.\n\nAnd let's not forget the **Adventure Dining Table** from CampBuddy. This isn't just a table; it's the centerpiece of your outdoor dining experience, transforming your campsite into a banquet hall under the open sky. Durable, portable, and easy to set up, it ensures your meals are just as memorable as your adventures.\n\nFrom the sleek allure of the **TrailBlaze Hiking Pants** keeping you stylish and comfortable on the trails, to the versatile companionship of the **CompactCook Camping Stove** ensuring you're well-fed on your journeys, every piece of gear is designed with your adventures in mind.\n\nSo, as you prepare to tackle the world's best cities and beyond, remember that the right gear doesn't just support your adventure\u2014it enhances it, making every moment more memorable. Gear up, step out, and let the adventures begin!"
    # research_result= {"web": [{"url": "https://www.timeout.com/things-to-do/best-cities-in-the-world", "name": "50 Best Cities in the World to Visit in 2024 - Time Out", "description": "The 50 best cities in the world for 2024. Photograph: Massimo Salesi / Shutterstock.com. 1. New York. What makes us great: You know it as \u2018the city that never sleeps\u2019 because many of its ..."}, {"url": "https://travel.usnews.com/rankings/worlds-best-cities-to-visit/", "name": "Best Cities in the World to Visit | U.S. News Travel", "description": "Lisbon. #27 in Best Cities in the World to Visit. Lisbon beckons to leisure travelers and digital nomads alike with its incredible vistas, colorful ceramic tiles and rich cultural heritage. Top ..."}, {"url": "https://travel.usnews.com/rankings/worlds-best-vacations/", "name": "30 World's Best Places to Visit for 2023-2024 | U.S. News Travel", "description": "Paris. #1 in World's Best Places to Visit for 2023-2024. France's magnetic City of Light is a perennial tourist destination, drawing visitors with its iconic attractions, like the Eiffel Tower and ..."}, {"url": "https://www.forbes.com/sites/laurabegleybloom/2023/12/14/ranked-the-100-best-cities-in-the-world-according-to-a-new-report/", "name": "Ranked: The 100 Best Cities In The World To Visit - Forbes", "description": "This was the first year that Washington D.C. made the list of 100 best places to travel. getty Trends in Travel. The report highlighted some of the big trends in travel, including sustainable tourism."}, {"url": "https://www.farandwide.com/s/best-places-visit-world-0697723328374f59", "name": "30 Best Travel Destinations in the World, Ranked | Far & Wide", "description": "Best Places to Visit in the World. The ultimate ranking of travel destinations aims to solve a serious problem: so many places to visit, so little time. But even in a world with a trillion destinations, some manage to stand out and rise to the top."}], "entities": [], "news": []}
    # product_documenation=[{"id": "cHJvZHVjdHMueGxzeDQ=", "title": "", "content": "Title: products.xlsx, and peace of mind. Be wild, be free, be cooked for with the CompactCook Camping Stove!\n\n", "url": "products.xlsx"}, {"id": "cHJvZHVjdHMueGxzeDM=", "title": "", "content": "Title: products.xlsx\tStep up your hiking game with HikeMate's TrailLite Daypack. Built for comfort and efficiency, this lightweight and durable backpack offers a spacious main compartment, multiple pockets, and organization-friendly features all in one sleek package. The adjustable shoulder straps and padded back panel ensure optimal comfort during those long exhilarating treks. Course through nature without worry as the daypack's water-resistant fabric protects your essentials from unexpected showers. Plus, never run dry with the integrated hydration system. And did we mention it comes in a plethora of colors and designs? So you can choose one that truly speaks to your outdoorsy soul! Keeping your visibility in mind, we've added reflective accents that light up in low-light conditions. Don't just carry a backpack, adorn a companion that takes you a step ahead in your adventures. Trust the TrailLite Daypack for a hassle-free, enjoyable hiking experience.\n\t17\tRainGuard Hiking Jacket\t110\tHiking Clothing\tMountainStyle\tIntroducing the MountainStyle RainGuard Hiking Jacket - the ultimate solution for weatherproof comfort during your outdoor undertakings! Designed with waterproof, breathable fabric, this jacket promises an outdoor experience that's as dry as it is comfortable. The rugged construction assures durability, while the adjustable hood provides a customizable fit against wind and rain. Featuring multiple pockets for safe, convenient storage and adjustable cuffs and hem, you can tailor the jacket to suit your needs on-the-go. And, don't worry about overheating during intense activities - it's equipped with ventilation zippers for increased airflow. Reflective details ensure visibility even during low-light conditions, making it perfect for evening treks. With its lightweight, packable design, carrying it inside your backpack requires minimal effort. With options for men and women, the RainGuard Hiking Jacket is perfect for hiking, camping, trekking and countless other outdoor adventures. Don't let the weather stand in your way - embrace the outdoors with MountainStyle RainGuard Hiking Jacket!\n\t18\tTrekStar Hiking Sandals\t70\tHiking Footwear\tTrekReady\tMeet the TrekStar Hiking Sandals from TrekReady - the ultimate trail companion for your feet. Designed for comfort and durability, these lightweight sandals are perfect for those who prefer to see the world from a hiking trail. They feature adjustable straps for a snug, secure fit, perfect for adapting to the contours of your feet. With a breathable design, your feet will stay cool and dry, escaping the discomfort of sweaty hiking boots on long summer treks. The deep tread rubber outsole ensures excellent traction on any terrain, while the cushioned footbed promises enhanced comfort with every step. For those wild and unpredictable trails, the added toe protection and shock-absorbing midsole protect your feet from rocky surprises. Ingeniously, the removable insole makes for easy cleaning and maintenance, extending the lifespan of your sandals. Available in various sizes and a handsome brown color, the versatile TrekStar Hiking Sandals are just as comfortable on a casual walk in the park as they are navigating rocky slopes. Explore more with TrekReady!\n\t19\tAdventure Dining Table\t90\tCamping Tables\tCampBuddy\tDiscover the joy of outdoor adventures with the CampBuddy Adventure Dining Table. This feature-packed camping essential brings both comfort and convenience to your memorable trips. Made from high-quality aluminum, it promises long-lasting performance, weather resistance, and easy maintenance - all key for the great outdoors! It's light, portable, and comes with adjustable height settings to suit various seating arrangements and the spacious surface comfortably accommodates meals, drinks, and other essentials. The sturdy yet lightweight frame holds food, dishes, and utensils with ease. When it's time to pack up, it fold and stows away with no fuss, ready for the next adventure!  Perfect for camping, picnics, barbecues, and beach outings - its versatility shines as brightly as the summer sun! Durable, sturdy and a breeze to set up, the Adventure Dining Table will be a loyal companion on every trip. Embark on your next adventure and make lifetime memories with CampBuddy. As with all good experiences, it'll leave you wanting more! \n\t20\tCompactCook Camping Stove\t60\tCamping Stoves\tCompactCook\tStep into the great outdoors with the CompactCook Camping Stove, a convenient, lightweight companion perfect for all your culinary camping needs. Boasting a robust design built for harsh environments, you can whip up meals anytime, anywhere. Its wind-resistant and fuel-versatile features coupled with an efficient cooking performance, ensures you won't have to worry about the elements or helpless taste buds while on adventures. The easy ignition technology and adjustable flame control make cooking as easy as a walk in the park, while its compact, foldable design makes packing a breeze. Whether you're camping with family or hiking solo, this reliable, portable stove is an essential addition to your gear. With its sturdy construction and safety-focused design, the CompactCook Camping Stove is a step above the rest, providing durability, quality", "url": "products.xlsx"}, {"id": "cHJvZHVjdHMueGxzeDE=", "title": "", "content": "Title: products.xlsx\tIntroducing EcoFire's Camping Stove, your ultimate companion for every outdoor adventure! This portable wonder is precision-engineered with a lightweight and compact design, perfect for capturing that spirit of wanderlust. Made from high-quality stainless steel, it promises durability and steadfast performance. This stove is not only fuel-efficient but also offers an easy, intuitive operation that ensures hassle-free cooking. Plus, it's flexible, accommodating a variety of cooking methods whether you're boiling, grilling, or simmering under the starry sky. Its stable construction, quick setup, and adjustable flame control make cooking a breeze, while safety features protect you from any potential mishaps. And did we mention it also includes an effective wind protector and a carry case for easy transportation? But that's not all! The EcoFire Camping Stove is eco-friendly, designed to minimize environmental impact. So get ready to enhance your camping experience and enjoy delicious outdoor feasts with this unique, versatile stove!\n\t7\tCozyNights Sleeping Bag\t100\tSleeping Bags\tCozyNights\tEmbrace the great outdoors in any season with the lightweight CozyNights Sleeping Bag! This durable three-season bag is superbly designed to give hikers, campers, and backpackers comfort and warmth during spring, summer, and fall. With a compact design that folds down into a convenient stuff sack, you can whisk it away on any adventure without a hitch. The sleeping bag takes comfort seriously, featuring a handy hood, ample room and padding, and a reliable temperature rating. Crafted from high-quality polyester, it ensures long-lasting use and can even be zipped together with another bag for shared comfort. Whether you're gazing at stars or catching a quick nap between trails, the CozyNights Sleeping Bag makes it a treat. Don't just sleep\u2014 dream with CozyNights.\n\t8\tAlpine Explorer Tent\t350\tTents\tAlpineGear\tWelcome to the joy of camping with the Alpine Explorer Tent! This robust, 8-person, 3-season marvel is from the responsible hands of the AlpineGear brand. Promising an enviable setup that is as straightforward as counting sheep, your camping experience is transformed into a breezy pastime. Looking for privacy? The detachable divider provides separate spaces at a moment's notice. Love a tent that breathes? The numerous mesh windows and adjustable vents fend off any condensation dragon trying to dampen your adventure fun. The waterproof assurance keeps you worry-free during unexpected rain dances. With a built-in gear loft to stash away your outdoor essentials, the Alpine Explorer Tent emerges as a smooth balance of privacy, comfort, and convenience. Simply put, this tent isn't just a shelter - it's your second home in the heart of nature! Whether you're a seasoned camper or a nature-loving novice, this tent makes exploring the outdoors a joyous journey.\n\t9\tSummitClimber Backpack\t120\tBackpacks\tHikeMate\tAdventure waits for no one! Introducing the HikeMate SummitClimber Backpack, your reliable partner for every exhilarating journey. With a generous 60-liter capacity and multiple compartments and pockets, packing is a breeze. Every feature points to comfort and convenience; the ergonomic design and adjustable hip belt ensure a pleasantly personalized fit, while padded shoulder straps protect you from the burden of carrying. Venturing into wet weather? Fear not! The integrated rain cover has your back, literally. Stay hydrated thanks to the backpack's hydration system compatibility. Travelling during twilight? Reflective accents keep you visible in low-light conditions. The SummitClimber Backpack isn't merely a carrier; it's a wearable base camp constructed from ruggedly durable nylon and thoughtfully designed for the great outdoors adventurer, promising to withstand tough conditions and provide years of service. So, set off on that quest - the wild beckons! The SummitClimber Backpack - your hearty companion on every expedition!\n\t10\tTrailBlaze Hiking Pants\t75\tHiking Clothing\tMountainStyle\tMeet the TrailBlaze Hiking Pants from MountainStyle, the stylish khaki champions of the trails. These are not just pants; they're your passport to outdoor adventure. Crafted from high-quality nylon fabric, these dapper troopers are lightweight and fast-drying, with a water-resistant armor that laughs off light rain. Their breathable design whisks away sweat while their articulated knees grant you the flexibility of a mountain goat. Zippered pockets guard your essentials, making them a hiker's best ally. Designed with durability for all your trekking trials, these pants come with a comfortable, ergonomic fit that will make you forget you're wearing them. Sneak a peek, and you are sure to be tempted by the sleek allure that is the TrailBlaze Hiking Pants. Your outdoors wardrobe wouldn't be quite complete without them.\n\t11\tTrailWalker Hiking Shoes\t110\tHiking Footwear\tTrekReady\tMeet the TrekReady TrailWalker Hiking Shoes, the ideal companion for all your outdoor adventures.", "url": "products.xlsx"}]
    if evaluate:
        evaluate_article_in_background(
            request=request,
            instructions=instructions,
            research=research_result,
            products=product_documenation,
            article=writer_response
        )

@trace
def test_write_article():
    context = "Can you find the latest camping trends and what folks are doing in the winter?"
    instructions = "Can you find the relevant information needed and good places to visit"
    for result in write_article(context, instructions, evaluate=True):
        print(*result)
    
if __name__ == "__main__":
    from api.logging import init_logging
    init_logging()
    test_write_article()

