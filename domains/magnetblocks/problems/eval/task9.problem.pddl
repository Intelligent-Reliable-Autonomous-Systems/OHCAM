(define (problem blocksworld-pick-place-task9)
(:domain blocksworld-pick-place)
(:objects
    blue_block yellow_block red_block green_block - block
    table_0 - table
    loc_00 loc_01 loc_02
    loc_10 loc_11 loc_12
    loc_20 loc_21 loc_22
    loc_30 loc_31 loc_32 - location)
(:init
    ; stack 1
    (on yellow_block table_0) (on green_block yellow_block)
    (at-loc yellow_block loc_11) (at-loc green_block loc_21)
    (obstructed-above loc_01) (obstructed-above loc_11)
    ; stack 2
    (on blue_block table_0) (on red_block blue_block)
    (at-loc blue_block loc_12) (at-loc red_block loc_22)
    (obstructed-above loc_02) (obstructed-above loc_12)

    ; block attributes
    (wooden green_block) (wooden yellow_block)
    (plastic red_block) (plastic blue_block)

    ; location relations
    (loc-above loc_10 loc_00) (loc-above loc_20 loc_10) (loc-above loc_30 loc_20)
    (loc-above loc_11 loc_01) (loc-above loc_21 loc_11) (loc-above loc_31 loc_21)
    (loc-above loc_12 loc_02) (loc-above loc_22 loc_12) (loc-above loc_32 loc_22)

    ; table occupies bottom row
    (at-loc table_0 loc_00) (at-loc table_0 loc_01) (at-loc table_0 loc_02)
)
(:goal
    ; "Make a 3 high stack in the middle with red on top."
    (and
        (obstructed-above loc_21)
        (at-loc red_block loc_31)
    )
)
)
