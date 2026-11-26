# Class balance and diversity

Counts are boxes, pixels, clips, report labels or modality occurrences as named. Ratios divide the largest observed count by the smallest positive count. “None” denotes an absent target.

| Task or stratum | Observed counts | Largest / smallest |
|---|---|---:|
| ESC-50 | airplane 40, breathing 40, brushing_teeth 40, can_opening 40, car_horn 40, cat 40, chainsaw 40, chirping_birds 40, church_bells 40, clapping 40, clock_alarm 40, clock_tick 40, coughing 40, cow 40, crackling_fire 40, crickets 40, crow 40, crying_baby 40, dog 40, door_wood_creaks 40, door_wood_knock 40, drinking_sipping 40, engine 40, fireworks 40, footsteps 40, frog 40, glass_breaking 40, hand_saw 40, helicopter 40, hen 40, insects 40, keyboard_typing 40, laughing 40, mouse_click 40, pig 40, pouring_water 40, rain 40, rooster 40, sea_waves 40, sheep 40, siren 40, sneezing 40, snoring 40, thunderstorm 40, toilet_flush 40, train 40, vacuum_cleaner 40, washing_machine 40, water_drops 40, wind 40 | 1.00 |
| FLAME | Fire 30,155, No_Fire 17,837 | 1.69 |
| FloodNet mask pixels | 0 553,694,755, 1 531,824,546, 2 916,732,387, 3 856,221,148, 4 1,613,072,447, 5 3,207,307,900, 6 5,126,886,702, 7 51,550,058, 8 58,288,146, 9 15,941,953,559 | 309.25 |
| HERIDAL boxes | person 3,194 | 1.00 |
| HumAID | caution_and_advice 5,394, displaced_people_and_evacuations 3,999, infrastructure_and_utility_damage 8,163, injured_or_dead_people 7,303, missing_or_found_people 358, not_humanitarian 6,296, other_relevant_information 12,144, requests_or_urgent_needs 2,618, rescue_volunteering_or_donation_effort 21,278, sympathy_and_support 8,931 | 59.44 |
| RescueNet mask pixels | 0 28,170,173,720, 1 4,358,798,120, 2 1,430,042,011, 3 1,411,706,150, 4 889,425,801, 5 768,173,839, 6 179,431,786, 7 3,763,278,379, 8 847,068,928, 9 12,144,273,059, 10 31,015,727 | 908.25 |
| SARD boxes | human 7,424 | 1.00 |
| Smoke | 0 17,873, 1 44,757 | 2.50 |
| WiSARD sidecar boxes | 0 69,603 | 1.00 |
| CrisisMMD damage | little_or_no_damage 475, mild_damage 839, severe_damage 2,212 | 4.66 |
| CrisisMMD humanitarian | affected_individuals 581, infrastructure_and_utility_damage 2,475, injured_or_dead_people 327, missing_or_found_people 33, not_humanitarian 6,998, other_relevant_information 4,477, rescue_volunteering_or_donation_effort 3,016, vehicle_damage 175 | 212.06 |
| CrisisMMD informative | informative 11,121, not_informative 6,961 | 1.60 |
| Native Model 1 findings | environment 4,132, hazard 1,991, possible_human 3,342 | 2.08 |
| expanded relationship | conflicting 63, corroborating 1,640, duplicate 12, related 1,999, single 1,261 | 166.58 |
| expanded assessment | None 1,679, hazard 375, possible_human 783, routine 1,927, uncertain_need 211 | 9.13 |
| expanded urgency | None 3,606, elevated 960, potentially_urgent 72, review_required 337 | 50.08 |
| expanded focal_modality | environment 2,504, image 3,770, thermal 2,051 | 1.84 |
| expanded agents | 1 542, 2 1,061, 3 1,124, 5 1,124, 8 1,124 | 2.07 |
| expanded scenario_id | cyclone_field 839, earthquake_field 854, flood_field 799, landslide_field 815, missing_person_field 812, wildfire_field 856 | 1.07 |
| expanded variant | conflict 6, native 4,951, relay 6, repeat 6, stale 6 | 825.17 |
| expanded provenance | rule_derived 4,969, unresolved 6 | 828.17 |
| expanded uncertainty | False 3,582, True 1,393 | 2.57 |
| expanded recommendation | False 3,606, True 1,369 | 2.63 |
| pilot relationship | conflicting 1, corroborating 170, duplicate 2, related 191, single 146 | 191.00 |
| pilot assessment | None 224, hazard 61, possible_human 42, routine 157, uncertain_need 26 | 8.62 |
| pilot urgency | None 381, elevated 64, potentially_urgent 9, review_required 56 | 42.33 |
| pilot focal_modality | environment 312, image 453, thermal 473 | 1.52 |
| pilot agents | 1 29, 3 321, 4 160 | 11.07 |
| pilot scenario_id | command_conflict 40, command_missing_modalities 40, command_routine 41, command_single 29, command_stale 36, cyclone_basic 40, earthquake_basic 40, flood_basic 44, flood_network_duplicate 40, flood_noise 40, flood_server_unavailable 40, landslide_basic 40, wildfire_basic 40 | 1.52 |
| pilot variant | conflict 1, native 505, relay 1, repeat 1, spurious 1, stale 1 | 505.00 |
| pilot provenance | rule_derived 508, unresolved 2 | 254.00 |
| pilot uncertainty | False 376, True 134 | 2.81 |
| pilot recommendation | False 381, True 129 | 2.95 |

HERIDAL has 560 empty annotation lists and SARD 832. Independent negatives are unavailable. FLAME No_Fire frames and negative Smoke alarms have different meanings. UCI and USGS have no hazard event targets. Every native pilot and field target has an empty missing-information list despite measured modality dropout. Distress and independently verified rescue outcomes have no class counts.

Future approved work could weight rare classes on training groups only, preserve evaluation prevalence and collect independent contradiction and uncertainty cases. Fleet sizes and disaster families are designed fixtures. Repeated layouts, adjacent frames and stationary sites limit generalization.
