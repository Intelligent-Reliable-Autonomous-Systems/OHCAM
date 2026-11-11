(define (problem blocksworld-train-05)
(:domain blocksworld-pick-place)
(:objects
    yellow pink red cyan - block
    table0 - table
    red_target blue_target green_target - target
    loc_a0 loc_a1 loc_a2 loc_a3 loc_a4 loc_b0 loc_b1 loc_b2 loc_b3 loc_b4 loc_c0 loc_c1 loc_c2 loc_c3 loc_c4 loc_d0 loc_d1 loc_d2 loc_d3 loc_d4 - location)
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
    (on cyan green_target)
    (at-loc cyan loc_c1)
    (obstructed-above loc_c0)
    ; stack 4
    (on yellow table0)
    (at-loc yellow loc_d1)
    (obstructed-above loc_d0)

    ; block attributes
    (wooden yellow)
    (plastic pink) (plastic red) (plastic cyan)

    ; location relations
    (loc-above loc_a1 loc_a0) (loc-above loc_a2 loc_a1) (loc-above loc_a3 loc_a2) (loc-above loc_a4 loc_a3)
    (loc-above loc_b1 loc_b0) (loc-above loc_b2 loc_b1) (loc-above loc_b3 loc_b2) (loc-above loc_b4 loc_b3)
    (loc-above loc_c1 loc_c0) (loc-above loc_c2 loc_c1) (loc-above loc_c3 loc_c2) (loc-above loc_c4 loc_c3)
    (loc-above loc_d1 loc_d0) (loc-above loc_d2 loc_d1) (loc-above loc_d3 loc_d2) (loc-above loc_d4 loc_d3)

    ; targets and table occupy the bottom row
    (at-loc red_target loc_a0) (at-loc blue_target loc_b0) (at-loc green_target loc_c0) (at-loc table0 loc_d0)
)
(:goal
    (and
        (on cyan red)
        (on red pink)
        (on pink blue_target)
        (on yellow table0)
    )
)
)
