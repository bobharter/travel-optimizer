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

   First cut at a prompt:   So the full prompt contract becomes:                                          
  1. Given: a city + free-text trip description
  2. Extract all named places, fix typos                                        
  3. For category intents, pick a well-known specific instance near one of the named destinations                                                            
  4. Return a structured list of concrete place names 