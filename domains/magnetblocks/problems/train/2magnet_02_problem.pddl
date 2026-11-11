(define (problem blocksworld-train-02)
(:domain blocksworld-pick-place)
(:objects
    yellow pink red - block
    red_target blue_target green_target - target
    loc_a0 loc_a1 loc_a2 loc_a3 loc_b0 loc_b1 loc_b2 loc_b3 loc_c0 loc_c1 loc_c2 loc_c3 - location)
(:init
    ; stack 1
    (on pink red_target)
    (at-loc pink loc_a1)
    (obstructed-above loc_a0)
    ; stack 2
    (on red blue_target)
    (at-loc red loc_b1)
    (obstructed-above loc_b0)
    ; stack 3
    (on yellow green_target)
    (at-loc yellow loc_c1)
    (obstructed-above loc_c0)

    ; block attributes
    (wooden yellow)
    (plastic pink) (plastic red)

    ; location relations
    (loc-above loc_a1 loc_a0) (loc-above loc_a2 loc_a1) (loc-above loc_a3 loc_a2)
    (loc-above loc_b1 loc_b0) (loc-above loc_b2 loc_b1) (loc-above loc_b3 loc_b2)
    (loc-above loc_c1 loc_c0) (loc-above loc_c2 loc_c1) (loc-above loc_c3 loc_c2)

    ; targets and table occupy the bottom row
    (at-loc red_target loc_a0) (at-loc blue_target loc_b0) (at-loc green_target loc_c0)
)
(:goal
    (and
        (on red pink)
        (on pink red_target)
        (on yellow green_target)
    )
)
)
