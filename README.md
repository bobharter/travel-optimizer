# Travel Optimizer

Django-based app to recommend optimal hotel locations based on travel distance to selected destinations

## Features (planned)
- Input a city and list of destinations
- Compute walking distances using mapping APIs
- Rank hotels based on total distance
- Optional AI-assisted destination extraction

## Tech Stack
- Python / Django
- Docker
- Google Maps APIs (initially)

## Status 
Initial development


Spec: 
User types something like: 

"I want to see the main historical sites, like the Pantheon and the Coliseum and the Vatcain and grab some good pasta."

  Extract destinations, where a destination is either:                          
  1. A named place (possibly misspelled) → normalize it                         
  2. A category/intent ("good pasta") → resolve it to a specific place instance 
                                                                               
  So Claude's job is to return a fully concrete list — no vague intents, all    
  real places — something like:                                                 
  ["Pantheon", "Colosseum", "Vatican", "Trattoria Dal Cavalier Gino"]           
                                                                                
  Where that last one is Claude's best guess at a well-known, well-located pasta
   restaurant in Rome. Then the user sees the full list and can swap it out if  
  they don't like the choice.                                                   
                                                                                
  This makes the AI demo even stronger — Claude is now doing disambiguation,    
  normalization, AND recommendation in one shot. And the confirmation step
  becomes more interesting because the user gets to see and react to the AI's   
  restaurant pick specifically.

  One design question worth settling before we implement: should Claude pick the
   restaurant based purely on reputation/fame (easiest, no Maps API needed yet),
   or should it try to pick one geographically near the other destinations? The 
  latter is the "right" answer but requires coordinates, which we don't have
  until Maps API is wired up.

  My suggestion: start with reputation ("well-known restaurant in Rome for      
  pasta"), make it work end-to-end, then swap in location-aware selection later.

Example input: I want to see the Vaticna, the Colissuem, and the Spansh Stps, and grab some excellent ravioli.          
I want to visit the Coliseum and the three highest-rated museums in town and the best art galleries and get some good pasta.  
I want to visit the best art galleries, eat the best dessert crepe, and for sur visite the Loovre and the Arc of Triumph. Oh, and the highest-rated museums.

   First cut at a prompt:   So the full prompt contract becomes:                                          
  1. Given: a city + free-text trip description
  2. Extract all named places, fix typos                                        
  3. For category intents, pick a well-known specific instance near one of the named destinations                                                            
  4. Return a structured list of concrete place names 


### Status as of 4-25-26 at 3pm (and Claude has this in its memory)

 What's built and working
                          
  - Free-text → LLM destination extraction (named + recommended, with alternatives dropdowns)
  - City validation before LLM call; city verification display on confirmation page                                                                           
  - Full 3-stage Maps pipeline: geocode destinations → find hotels → rank by walking distance                                                                 
  - Results page: ranked hotel list + interactive map, A/B/C markers, per-destination breakdown                                                               
  - Google Hotels + Booking.com links on each hotel card                                                                                                      
  - Price range filter (limited effect — Google rarely returns price data for hotels)                                                                         
  - Imperial/metric units based on destination country                                                                                                        
  - Map picker modal (just built): POI clicks + search box, green overlay markers, lazy init                                                                  
                                                                                                                                                              
  ---                                                                                                                                                         
  Three items identified this session (ready to code)                                                                                                         
                                                                                                                                                              
  1. Links for manually-added/map-picked destinations (easy) — these currently show as plain text in the results legend because data-url is empty; fix by  generating a Google search URL in JS when adding them                                                                                                       
  2. Add destinations on results page (moderate) — "Add destination" input re-POSTs to /results/ with all current destinations + the new one; needs  city_lat/city_lng passed through to the results template                                                                                                    
  3. Booking.com shows Euros (easy) — add &selected_currency=USD to the Booking.com URL for US trips; pass units to the results template context
                                                                                                                                                              
  ---             
  Longer-term roadmap                                                                                                                                         
                     
  - Geocoding failure warnings on results page
  - Vacation rental filtering (switch "lodging" → "hotel" in Places API — confirm with colleague)                                                             
  - Real pricing via Amadeus Hotel Offers API (requires check-in/check-out dates) — wife strongly wants prices                                                
  - Outlier detection for bad geocodes (e.g. "Seine River" geocoding 775km from Paris)                                                                        
  - LLM prompt improvement: append city name to geographic features (rivers, parks, lakes)                                                                    
  - Docker deployment                                                                                                                                         
  - Split-pane home page (map + free-text side by side from the start — mobile layout needs separate design)                                                  
  - Map mode on results page (live re-ranking as user adds destinations)                                                                                      
                                                                                                                                                              
  ---                                                                                                                                                         
  Known limitations                                                                                                                                           
                   
  - Google rarely returns price_level for hotels — price filter mostly ineffective
  - LLM may hallucinate destinations — confirmation page is the safeguard                                                                                     
  - Activity-based inputs ("take a cruise") don't geocode well — users guided to map picker instead                                                           
                                                                                                                                                              
✻ Sautéed for 38s                                                                                                                                             
                                                                                                                                                              
※ recap: Building a hotel optimizer app that ranks hotels by walking distance to your destinations. Map picker modal is done and committed; next up is fixing 
  destination links, adding destinations from the results page, and correcting Booking.com currency.                                                          
          