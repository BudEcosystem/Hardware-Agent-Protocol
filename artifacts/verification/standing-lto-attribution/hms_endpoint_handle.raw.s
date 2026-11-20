hms_endpoint_handle:
.LFB174:
	.loc 1 370 0
	.cfi_startproc
.LVL1645:
	push r2
.LCFI691:
	.cfi_def_cfa_offset 3
	.cfi_offset 2, -2
	push r3
.LCFI692:
	.cfi_def_cfa_offset 4
	.cfi_offset 3, -3
	push r4
.LCFI693:
	.cfi_def_cfa_offset 5
	.cfi_offset 4, -4
	push r5
.LCFI694:
	.cfi_def_cfa_offset 6
	.cfi_offset 5, -5
	push r6
.LCFI695:
	.cfi_def_cfa_offset 7
	.cfi_offset 6, -6
	push r7
.LCFI696:
	.cfi_def_cfa_offset 8
	.cfi_offset 7, -7
	push r8
.LCFI697:
	.cfi_def_cfa_offset 9
	.cfi_offset 8, -8
	push r9
.LCFI698:
	.cfi_def_cfa_offset 10
	.cfi_offset 9, -9
	push r10
.LCFI699:
	.cfi_def_cfa_offset 11
	.cfi_offset 10, -10
	push r11
.LCFI700:
	.cfi_def_cfa_offset 12
	.cfi_offset 11, -11
	push r12
.LCFI701:
	.cfi_def_cfa_offset 13
	.cfi_offset 12, -12
	push r13
.LCFI702:
	.cfi_def_cfa_offset 14
	.cfi_offset 13, -13
	push r14
.LCFI703:
	.cfi_def_cfa_offset 15
	.cfi_offset 14, -14
	push r15
.LCFI704:
	.cfi_def_cfa_offset 16
	.cfi_offset 15, -15
	push r16
.LCFI705:
	.cfi_def_cfa_offset 17
	.cfi_offset 16, -16
	push r17
.LCFI706:
	.cfi_def_cfa_offset 18
	.cfi_offset 17, -17
	push r28
.LCFI707:
	.cfi_def_cfa_offset 19
	.cfi_offset 28, -18
	push r29
.LCFI708:
	.cfi_def_cfa_offset 20
	.cfi_offset 29, -19
	in r28,__SP_L__
	in r29,__SP_H__
.LCFI709:
	.cfi_def_cfa_register 28
	sbiw r28,63
.LCFI710:
	.cfi_def_cfa_offset 83
	in __tmp_reg__,__SREG__
	cli
	out __SP_H__,r29
	out __SREG__,__tmp_reg__
	out __SP_L__,r28
/* prologue: function */
/* frame size = 63 */
/* stack size = 81 */
.L__stack_usage = 81
	movw r4,r24
	std Y+25,r22
	std Y+9,r20
	std Y+20,r14
	std Y+21,r15
	std Y+22,r16
	std Y+23,r17
	std Y+24,r18
	std Y+12,r19
	std Y+51,r8
	std Y+52,r9
	std Y+53,r10
	std Y+54,r11
	adiw r28,84-62
	ldd r6,Y+62
	ldd r7,Y+63
	sbiw r28,84-62
	adiw r28,88-63
	ldd r16,Y+63
	sbiw r28,88-63
	adiw r28,89-63
	ldd r17,Y+63
	sbiw r28,89-63
	adiw r28,90-63
	ldd r18,Y+63
	sbiw r28,90-63
	adiw r28,91-63
	ldd r19,Y+63
	sbiw r28,91-63
	adiw r28,92-63
	ldd r20,Y+63
	sbiw r28,92-63
.LVL1646:
	adiw r28,93-63
	ldd r21,Y+63
	sbiw r28,93-63
	adiw r28,94-63
	ldd r26,Y+63
	sbiw r28,94-63
	adiw r28,95-63
	ldd r27,Y+63
	sbiw r28,95-63
	adiw r28,96-63
	ldd r14,Y+63
	sbiw r28,96-63
	adiw r28,97-63
	ldd r15,Y+63
	sbiw r28,97-63
	adiw r28,98-62
	ldd r2,Y+62
	ldd r3,Y+63
	sbiw r28,98-62
	.loc 1 372 0
	adiw r28,100-62
	ldd r10,Y+62
	ldd r11,Y+63
	sbiw r28,100-62
	cp r10,__zero_reg__
	cpc r11,__zero_reg__
	breq .L1431
	movw r30,r10
	std Z+1,__zero_reg__
	st Z,__zero_reg__
.L1431:
	.loc 1 373 0
	cp r4,__zero_reg__
	cpc r5,__zero_reg__
	brne .L1432
.LVL1647:
.L1434:
	.loc 1 378 0
	std Y+11,__zero_reg__
.LVL1648:
.L1430:
	.loc 1 442 0
	ldd r24,Y+11
/* epilogue start */
	adiw r28,63
	in __tmp_reg__,__SREG__
	cli
	out __SP_H__,r29
	out __SREG__,__tmp_reg__
	out __SP_L__,r28
	pop r29
	pop r28
	pop r17
	pop r16
	pop r15
	pop r14
	pop r13
	pop r12
	pop r11
	pop r10
	pop r9
	pop r8
	pop r7
	pop r6
	pop r5
	pop r4
	pop r3
	pop r2
	ret
.LVL1649:
.L1432:
	.loc 1 373 0
	movw r30,r4
	ld r24,Z
	ldd r25,Z+1
	or r24,r25
	breq .L1434
	movw r10,r4
	ldi r31,116
	add r10,r31
	adc r11,__zero_reg__
	movw r30,r10
	ld r24,Z
	cpse r24,__zero_reg__
	rjmp .L1435
	.loc 1 374 0
	movw r30,r4
	ldd r24,Z+2
	ldd r25,Z+3
	.loc 1 373 0
	sbiw r24,0
	brne .+2
	rjmp .L1435
	.loc 1 374 0
	cp r6,__zero_reg__
	cpc r7,__zero_reg__
	brne .+2
	rjmp .L1435
	adiw r28,86-62
	ldd r22,Y+62
	ldd r23,Y+63
	sbiw r28,86-62
.LVL1650:
	subi r22,2
	sbc r23,__zero_reg__
	cpi r22,-65
	cpc r23,__zero_reg__
	brsh .L1435
	.loc 1 375 0
	movw r30,r6
	ld r22,Z
	cpi r22,lo8(2)
	brne .L1435
	.loc 1 376 0
	adiw r28,101-63
	ldd r31,Y+63
	sbiw r28,101-63
	push r31
	adiw r28,100-63
	ldd r10,Y+63
	sbiw r28,100-63
	push r10
	push r3
	push r2
	push r15
	push r14
	push r27
	push r26
	push r21
	push r20
	push r19
	push r18
	push r17
	push r16
	adiw r28,87-63
	ldd r11,Y+63
	sbiw r28,87-63
	push r11
	adiw r28,86-63
	ldd r14,Y+63
	sbiw r28,86-63
	push r14
	push r7
	push r6
	ldd r8,Y+51
	ldd r9,Y+52
	ldd r10,Y+53
	ldd r11,Y+54
.LVL1651:
	ldd r14,Y+20
	ldd r15,Y+21
	ldd r16,Y+22
	ldd r17,Y+23
	ldd r18,Y+24
	ldd r19,Y+12
	ldd r20,Y+9
	ldd r22,Y+25
	call hms_standing_handle
.LVL1652:
	std Y+11,r24
	in __tmp_reg__,__SREG__
	cli
	out __SP_H__,r29
	out __SREG__,__tmp_reg__
	out __SP_L__,r28
	rjmp .L1430
.LVL1653:
.L1435:
	.loc 1 378 0
	movw r30,r10
	ld r24,Z
	cpse r24,__zero_reg__
	rjmp .L1434
	cp r6,__zero_reg__
	cpc r7,__zero_reg__
	brne .+2
	rjmp .L1434
	adiw r28,86-62
	ldd r24,Y+62
	ldd r25,Y+63
	sbiw r28,86-62
	sbiw r24,2
	cpi r24,-65
	cpc r25,__zero_reg__
	brlo .+2
	rjmp .L1434
	movw r30,r6
	ldd r22,Z+1
.LVL1654:
.LBB1150:
.LBB1151:
	.loc 1 236 0
	cpi r22,lo8(1)
	breq .L1621
	.loc 1 235 0
	ldi r25,lo8(-16)
	add r25,r22
	cpi r25,lo8(3)
	brlo .L1621
	subi r22,lo8(-(-32))
.LVL1655:
	ldi r24,lo8(1)
	ldi r25,0
	cpi r22,lo8(4)
	brlo .L1437
	ldi r25,0
	ldi r24,0
.L1437:
.LVL1656:
.LBE1151:
.LBE1150:
	.loc 1 378 0
	or r24,r25
	brne .+2
	rjmp .L1434
.L1621:
	.loc 1 379 0
	movw r22,r26
	movw r24,r4
	call update
.LVL1657:
	movw r26,r6
	adiw r26,1
	ld r27,X
	std Y+11,r27
.LVL1658:
.LBB1152:
.LBB1153:
	.loc 1 213 0
	movw r30,r6
	ld r24,Z
	cpi r24,lo8(1)
	brne .L1506
.LVL1659:
	.loc 1 214 0
	cpi r27,lo8(18)
	breq .L1439
	brsh .L1440
	cpi r27,lo8(16)
	brne .+4
	jmp .L1441
	brlo .+4
	jmp .L1500
.LBE1153:
.LBE1152:
	.loc 1 215 0
	ldi r24,lo8(2)
	ldi r25,0
.LBB1165:
.LBB1158:
	.loc 1 214 0
	cpi r27,lo8(1)
	breq .L1445
.L1506:
.LBE1158:
.LBE1165:
	.loc 1 213 0
	ldi r24,lo8(1)
	rjmp .L1438
.L1440:
.LBB1166:
.LBB1159:
	.loc 1 214 0
	ldd r31,Y+11
	cpi r31,lo8(32)
	breq .L1444
	brlo .L1506
.LBE1159:
.LBE1166:
	.loc 1 219 0
	ldi r24,lo8(44)
	ldi r25,0
.LBB1167:
.LBB1160:
	.loc 1 214 0
	cpi r31,lo8(36)
	brsh .L1506
.L1445:
.LVL1660:
	.loc 1 229 0
	adiw r28,86-62
	ldd r10,Y+62
	ldd r11,Y+63
	sbiw r28,86-62
	cp r10,r24
	cpc r11,r25
	brne .L1566
	.loc 1 230 0
	ldd r16,Y+11
	cpi r16,lo8(1)
	brne .+2
	rjmp .L1513
.LVL1661:
.L1495:
	movw r24,r6
	adiw r24,2
	call get32
.LVL1662:
	or r22,r23
	or r22,r24
	or r22,r25
	breq .L1511
	movw r26,r6
	adiw r26,6
	ld r24,X+
	ld r25,X
	or r24,r25
	breq .L1511
	.loc 1 231 0
	ldd r27,Y+11
	cpi r27,lo8(32)
	brsh .+2
	rjmp .L1513
	movw r24,r6
	adiw r24,8
	call get32
.LVL1663:
	or r22,r23
	or r22,r24
	or r22,r25
	breq .+2
	rjmp .L1513
.L1511:
.LBE1160:
.LBE1167:
	.loc 1 230 0
	ldi r24,lo8(11)
	rjmp .L1438
.LVL1664:
.L1439:
	.loc 1 218 0
	ldi r24,lo8(10)
	ldi r25,0
.L1442:
.LVL1665:
.LBB1168:
.LBB1161:
	.loc 1 229 0
	adiw r28,86-62
	ldd r10,Y+62
	ldd r11,Y+63
	sbiw r28,86-62
	cp r10,r24
	cpc r11,r25
	breq .L1495
.LVL1666:
.L1566:
.LBE1161:
.LBE1168:
	.loc 1 221 0
	ldi r24,lo8(2)
	rjmp .L1438
.L1444:
.LBB1169:
.LBB1162:
	adiw r28,86-62
	ldd r16,Y+62
	ldd r17,Y+63
	sbiw r28,86-62
	cpi r16,88
	cpc r17,__zero_reg__
	brlo .L1566
	movw r26,r6
	adiw r26,47
	ld r18,X
	sbiw r26,47
	cpi r18,lo8(73)
	brsh .L1566
	.loc 1 222 0
	adiw r26,46
	ld r25,X
.LVL1667:
.LBE1162:
.LBE1169:
	.loc 1 41 0
	ldi r24,0
.LVL1668:
.L1446:
.LBB1170:
.LBB1163:
.LBB1154:
.LBB1155:
	.loc 1 42 0
	cpse r25,__zero_reg__
	rjmp .L1447
.LVL1669:
.LBE1155:
.LBE1154:
	.loc 1 223 0
	movw r30,r6
	ldd r25,Z+49
	cpse r25,__zero_reg__
	rjmp .L1505
	ldd r20,Z+50
	ldd r21,Z+51
	or r20,r21
	brne .L1505
	.loc 1 224 0
	ldd r25,Z+48
	cpi r25,lo8(2)
	brlo .+2
	rjmp .L1506
	.loc 1 225 0
	ldd r20,Z+44
	ldd r21,Z+45
	or r20,r21
	brne .+2
	rjmp .L1507
	.loc 1 222 0
	ldi r25,0
	adiw r24,22
.LVL1670:
	lsl r24
	rol r25
	lsl r24
	rol r25
	add r24,r18
	adc r25,__zero_reg__
	rjmp .L1442
.LVL1671:
.L1447:
.LBB1157:
.LBB1156:
	.loc 1 42 0
	mov r19,r25
	andi r19,lo8(1)
	add r24,r19
.LVL1672:
	lsr r25
.LVL1673:
	rjmp .L1446
.LVL1674:
.L1505:
.LBE1156:
.LBE1157:
.LBE1163:
.LBE1170:
	.loc 1 223 0
	ldi r24,lo8(3)
.LVL1675:
.L1438:
	.loc 1 384 0
	movw r30,r4
	ldd r8,Z+2
	ldd r9,Z+3
.LVL1676:
	cp r8,__zero_reg__
	cpc r9,__zero_reg__
	breq .L1448
	movw r26,r8
	adiw r26,4
	ld r25,X
	cpi r25,lo8(2)
	brne .+2
	rjmp .L1514
.L1448:
	.loc 1 386 0
	cpse r24,__zero_reg__
	rjmp .L1515
	ldd r27,Y+25
	cpi r27,lo8(1)
	breq .+2
	rjmp .L1516
	ldd r30,Y+9
	cpse r30,__zero_reg__
	rjmp .L1517
.LVL1677:
	.loc 1 387 0
	ldd r30,Y+11
	cpi r30,lo8(1)
	breq .+2
	rjmp .L1656
	movw r18,r12
	ldd r20,Y+20
	ldd r21,Y+21
	ldd r22,Y+22
	ldd r23,Y+23
	ldd r24,Y+24
	ldd r25,Y+12
	ldi r26,0
	call __cmpdi2_s8
	breq .L1449
	ldi r31,lo8(5)
	std Y+9,r31
.LVL1678:
.L1449:
	.loc 1 393 0
	movw r30,r4
	ldd r24,Z+36
	ldd r25,Z+37
	ldd r26,Z+38
	ldd r27,Z+39
	cpi r24,-1
	sbci r25,-1
	sbci r26,-1
	sbci r27,-1
	breq .+2
	rjmp .L1451
	.loc 1 394 0
	ldi r22,lo8(12)
	movw r24,r4
	call fault
.LVL1679:
	.loc 1 395 0
	ldd r16,Y+11
	cpi r16,lo8(34)
	brne .+2
	rjmp .L1452
	cpi r16,lo8(18)
	breq .+2
	rjmp .L1434
	.loc 1 397 0
	ldd r11,Y+9
	cpse r11,__zero_reg__
	rjmp .L1454
.L1455:
	.loc 1 402 0
	movw r26,r6
	adiw r26,8
	ld r24,X+
	ld r25,X
	ldi r20,lo8(3)
	cp r24,__zero_reg__
	sbci r25,6
	breq .+2
	rjmp .L1663
	.loc 1 403 0
	movw r22,r6
	movw r24,r4
	call context_matches
.LVL1680:
	tst r24
	brne .+2
	rjmp .L1466
	.loc 1 404 0
	movw r30,r4
	subi r30,-109
	sbci r31,-1
	ld r24,Z
	tst r24
	brne .+2
	rjmp .L1468
	movw r16,r4
	subi r16,-108
	sbci r17,-1
	movw r30,r16
	ld r24,Z
	subi r24,lo8(-(-1))
	cpi r24,lo8(2)
	brlo .+2
	rjmp .L1468
	.loc 1 405 0
	ldi r22,lo8(6)
	movw r24,r4
	call invalidate
.LVL1681:
	movw r26,r16
	ld r24,X
	cpi r24,lo8(4)
	brne .+2
	rjmp .L1526
.LVL1682:
.L1485:
	.loc 1 259 0
	std Y+9,__zero_reg__
	rjmp .L1454
.LVL1683:
.L1507:
	.loc 1 225 0
	ldi r24,lo8(10)
.LVL1684:
	rjmp .L1438
.LVL1685:
.L1513:
	.loc 1 232 0
	ldi r24,0
	rjmp .L1438
.LVL1686:
.L1656:
	.loc 1 389 0
	movw r30,r4
	subi r30,-74
	sbci r31,-1
	ld r24,Z
	sbrs r24,0
	rjmp .L1518
	.loc 1 390 0
	movw r26,r4
	adiw r26,4
	ld r18,X
	sbiw r26,4
	adiw r26,5
	ld r19,X
	sbiw r26,5
	adiw r26,6
	ld r20,X
	sbiw r26,6
	adiw r26,7
	ld r21,X
	sbiw r26,7
	adiw r26,8
	ld r22,X
	sbiw r26,8
	adiw r26,9
	ld r23,X
	sbiw r26,9
	adiw r26,10
	ld r24,X
	sbiw r26,10
	adiw r26,11
	ld r25,X
	movw r10,r12
	ldd r12,Y+20
.LVL1687:
	ldd r13,Y+21
	ldd r14,Y+22
	ldd r15,Y+23
	ldd r16,Y+24
	ldd r17,Y+12
	call __cmpdi2
	brne .L1519
	.loc 1 391 0
	ldd r10,Y+51
	ldd r11,Y+52
	ldd r12,Y+53
	ldd r13,Y+54
	or r10,r11
	or r10,r12
	or r10,r13
	breq .+2
	rjmp .L1449
	ldi r21,lo8(11)
	std Y+9,r21
.LVL1688:
	rjmp .L1449
.LVL1689:
.L1514:
	.loc 1 385 0
	ldi r16,lo8(1)
	std Y+9,r16
.LVL1690:
	rjmp .L1449
.LVL1691:
.L1515:
	.loc 1 386 0
	std Y+9,r24
.LVL1692:
	rjmp .L1449
.LVL1693:
.L1516:
	.loc 1 385 0
	ldi r17,lo8(1)
	std Y+9,r17
.LVL1694:
	rjmp .L1449
.LVL1695:
.L1517:
	ldi r18,lo8(1)
	std Y+9,r18
.LVL1696:
	rjmp .L1449
.LVL1697:
.L1518:
	.loc 1 389 0
	ldi r19,lo8(18)
	std Y+9,r19
.LVL1698:
	rjmp .L1449
.LVL1699:
.L1519:
	.loc 1 387 0
	ldi r20,lo8(5)
	std Y+9,r20
.LVL1700:
	rjmp .L1449
.LVL1701:
.L1451:
	.loc 1 397 0
	ldd r17,Y+9
	cpse r17,__zero_reg__
	rjmp .L1454
	ldd r18,Y+11
	cpi r18,lo8(18)
	brne .+2
	rjmp .L1455
	brsh .L1456
	cpi r18,lo8(16)
	brne .+2
	rjmp .L1457
	brlo .+2
	rjmp .L1458
	cpi r18,lo8(1)
	brne .+2
	rjmp .L1454
.L1521:
	.loc 1 426 0
	ldi r16,lo8(1)
	rjmp .L1660
.L1456:
	.loc 1 397 0
	ldd r19,Y+11
	cpi r19,lo8(33)
	brne .+2
	rjmp .L1460
	brlo .+2
	rjmp .L1461
	cpi r19,lo8(32)
	brne .L1521
.LVL1702:
.LBB1171:
.LBB1172:
	.loc 1 270 0
	movw r24,r6
	adiw r24,8
	call get32
.LVL1703:
	std Y+47,r22
	std Y+48,r23
	std Y+49,r24
	std Y+50,r25
.LVL1704:
	movw r24,r6
	subi r24,-76
	sbci r25,-1
	call get32
.LVL1705:
	movw r12,r22
	movw r14,r24
.LVL1706:
	.loc 1 271 0
	movw r24,r6
	adiw r24,52
	call get64
.LVL1707:
	std Y+55,r18
	std Y+56,r19
	std Y+57,r20
	std Y+58,r21
	std Y+59,r22
	std Y+60,r23
	std Y+61,r24
	std Y+62,r25
.LVL1708:
	movw r24,r6
.LVL1709:
	adiw r24,60
	call get64
.LVL1710:
	std Y+36,r18
	std Y+37,r19
	std Y+38,r20
	std Y+39,r21
	std Y+40,r22
	std Y+41,r23
	std Y+42,r24
	std Y+43,r25
.LVL1711:
	movw r24,r6
.LVL1712:
	subi r24,-68
	sbci r25,-1
	call get64
.LVL1713:
	std Y+30,r18
	std Y+31,r19
	std Y+32,r20
	std Y+33,r21
	std Y+34,r22
	std Y+44,r23
	std Y+45,r24
	std Y+46,r25
.LVL1714:
	movw r24,r6
.LVL1715:
	subi r24,-80
	sbci r25,-1
	call get64
.LVL1716:
	std Y+20,r18
	std Y+21,r19
	std Y+22,r20
	std Y+23,r21
	std Y+24,r22
	std Y+12,r23
	std Y+25,r24
.LVL1717:
	std Y+35,r25
.LVL1718:
	.loc 1 274 0
	movw r30,r4
	subi r30,-110
	sbci r31,-1
	ld r17,Z
	tst r17
	brne .+2
	rjmp .L1470
	movw r24,r4
.LVL1719:
	subi r24,-125
	sbci r25,-1
	call get32
.LVL1720:
	ldd r18,Y+47
	ldd r19,Y+48
	ldd r20,Y+49
	ldd r21,Y+50
	cp r18,r22
	cpc r19,r23
	cpc r20,r24
	cpc r21,r25
	breq .+2
	rjmp .L1470
	.loc 1 275 0
	adiw r28,86-62
	ldd r20,Y+62
	ldd r21,Y+63
	sbiw r28,86-62
	cp r17,r20
	cpc __zero_reg__,r21
	breq .+2
	rjmp .L1527
	movw r22,r6
	movw r24,r4
	subi r24,-117
	sbci r25,-1
	call memcmp
.LVL1721:
.LBE1172:
.LBE1171:
	ldi r21,lo8(9)
.LBB1191:
.LBB1184:
	or r24,r25
	brne .+2
	rjmp .L1454
.LVL1722:
.L1665:
.LBE1184:
.LBE1191:
	.loc 1 405 0
	std Y+9,r21
	rjmp .L1454
.LVL1723:
.L1461:
	.loc 1 397 0
	ldd r20,Y+11
	cpi r20,lo8(34)
	brne .+2
	rjmp .L1463
	cpi r20,lo8(35)
	breq .+2
	rjmp .L1521
	.loc 1 417 0
	movw r22,r6
	movw r24,r4
	call reference.lto_priv.15
.LVL1724:
	std Y+9,r24
.LVL1725:
	.loc 1 418 0
	cpse r24,__zero_reg__
	rjmp .L1454
	movw r30,r4
	subi r30,-83
	sbci r31,-2
.LBB1192:
.LBB1193:
	.loc 1 51 0
	ld r24,Z
.LVL1726:
	subi r24,lo8(-(-3))
.LBE1193:
.LBE1192:
	.loc 1 418 0
	cpi r24,lo8(4)
	brlo .+2
	rjmp .L1562
	adiw r30,4
	ld r10,Z
	std Y+9,r10
.LVL1727:
	cpse r10,__zero_reg__
	rjmp .L1563
	sbiw r30,1
	ld r24,Z
	cpi r24,lo8(3)
	brne .+2
	rjmp .L1564
.LVL1728:
	.loc 1 420 0
	subi r30,-24
	sbc r31,__zero_reg__
	st Z,__zero_reg__
	ldi r24,lo8(69)
	subi r30,57
	sbci r31,-1
	movw r26,r30
	0:
	st X+,__zero_reg__
	dec r24
	brne 0b
	subi r30,-58
	sbc r31,__zero_reg__
	st Z,__zero_reg__
	.loc 1 421 0
	cp r8,__zero_reg__
	cpc r9,__zero_reg__
	breq .L1487
.LVL1729:
.LBB1194:
.LBB1195:
	.loc 11 186 0
	movw r30,r8
	ldd r24,Z+4
	cpi r24,lo8(2)
	breq .L1487
	std Z+4,__zero_reg__
.LVL1730:
.L1487:
.LBE1195:
.LBE1194:
	.loc 1 422 0
	movw r24,r4
	call drain_state
.LVL1731:
	.loc 1 423 0
	movw r30,r4
	ldd r24,Z+32
	ldd r25,Z+33
	ldd r26,Z+34
	ldd r27,Z+35
	cpi r24,-1
	sbci r25,-1
	sbci r26,-1
	sbci r27,-1
	breq .+2
	rjmp .L1485
	ldi r22,lo8(12)
	movw r24,r4
	call fault
.LVL1732:
	rjmp .L1454
.LVL1733:
.L1457:
	.loc 1 399 0
	movw r22,r6
	movw r24,r4
	call bind_context
.LVL1734:
.L1658:
	.loc 1 418 0
	std Y+9,r24
	rjmp .L1454
.LVL1735:
.L1458:
.LBB1196:
.LBB1197:
	.loc 1 255 0
	movw r30,r4
	subi r30,-74
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	call readiness.isra.2
.LVL1736:
	std Y+9,r24
.LVL1737:
	.loc 1 256 0
	movw r24,r6
.LVL1738:
	adiw r24,40
	call get64
.LVL1739:
	std Y+10,r18
	std Y+20,r19
	movw r8,r20
	std Y+21,r22
	std Y+22,r23
	std Y+23,r24
	std Y+24,r25
.LVL1740:
	.loc 1 257 0
	ldd r21,Y+9
	cpse r21,__zero_reg__
	rjmp .L1454
	.loc 1 258 0
	movw r22,r6
.LVL1741:
	movw r24,r4
.LVL1742:
	call context_matches
.LVL1743:
	cpse r24,__zero_reg__
	rjmp .L1465
.LVL1744:
.L1466:
.LBE1197:
.LBE1196:
	ldi r22,lo8(6)
.LVL1745:
.L1661:
	.loc 1 418 0
	std Y+9,r22
	rjmp .L1454
.LVL1746:
.L1465:
.LBB1200:
.LBB1198:
	.loc 1 258 0
	movw r22,r6
	subi r22,-8
	sbci r23,-1
	ldi r20,lo8(32)
	ldi r21,0
	movw r24,r4
	subi r24,-76
	sbci r25,-1
	call memcmp
.LVL1747:
	or r24,r25
	brne .L1466
	.loc 1 259 0
	movw r30,r4
	subi r30,-109
	sbci r31,-1
	ld r24,Z
	cpse r24,__zero_reg__
	rjmp .L1467
.LVL1748:
.L1468:
.LBE1198:
.LBE1200:
	ldi r24,lo8(4)
	rjmp .L1658
.LVL1749:
.L1467:
.LBB1201:
.LBB1199:
	movw r30,r4
	subi r30,-108
	sbci r31,-1
	ld r24,Z
	subi r24,lo8(-(-1))
	cpi r24,lo8(2)
	brsh .L1468
	.loc 1 260 0
	ldd r18,Y+10
	ldd r19,Y+20
	movw r20,r8
	ldd r22,Y+21
	ldd r23,Y+22
	ldd r24,Y+23
	ldd r25,Y+24
	ldi r26,lo8(-1)
	call __cmpdi2_s8
	brne .+2
	rjmp .L1522
	movw r26,r4
	adiw r26,12
	ld r27,X
	std Y+12,r27
	movw r30,r4
	ldd r31,Z+13
	std Y+25,r31
.LVL1750:
	movw r26,r4
	adiw r26,14
	ld r6,X
	sbiw r26,14
.LVL1751:
	adiw r26,15
	ld r7,X
	sbiw r26,15
	adiw r26,16
	ld r27,X
	movw r30,r4
	ldd r26,Z+17
	ldd r31,Z+18
	std Y+26,r31
	movw r30,r4
	ldd r31,Z+19
	std Y+28,r31
	ldd r10,Y+12
	ldd r11,Y+25
	movw r12,r6
	mov r14,r27
	mov r15,r26
	ldd r16,Y+26
	mov r17,r31
	call __cmpdi2
	breq .+2
	brsh .+2
	rjmp .L1523
	call __subdi3
	movw r26,r4
	ld r30,X+
	ld r31,X
	sbiw r26,1
	ldd r10,Z+12
	ldd r11,Z+13
	ldd r12,Z+14
	ldd r13,Z+15
	movw r14,r12
	movw r12,r14
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	movw r16,r14
	std Y+12,r10
	std Y+13,r11
	std Y+14,r12
	std Y+15,r13
	std Y+16,r14
	std Y+17,r15
	std Y+18,r16
	std Y+19,r17
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __cmpdi2
	breq .+4
	brlo .+2
	rjmp .L1524
	.loc 1 262 0
	adiw r26,20
	ld r10,X
	sbiw r26,20
	adiw r26,21
	ld r11,X
	sbiw r26,21
	adiw r26,22
	ld r12,X
	sbiw r26,22
	adiw r26,23
	ld r13,X
	sbiw r26,23
	adiw r26,24
	ld r14,X
	sbiw r26,24
	adiw r26,25
	ld r15,X
	sbiw r26,25
	adiw r26,26
	ld r16,X
	sbiw r26,26
	adiw r26,27
	ld r17,X
	sbiw r26,27
	ldd r18,Y+10
	ldd r19,Y+20
	movw r20,r8
	ldd r22,Y+21
	ldd r23,Y+22
	ldd r24,Y+23
	ldd r25,Y+24
	call __cmpdi2
	breq .L1469
	brlo .L1469
	adiw r26,20
	st X,r18
	sbiw r26,20
	adiw r26,21
	st X,r19
	sbiw r26,21
	adiw r26,22
	st X,r8
	sbiw r26,22
	adiw r26,23
	st X,r9
	sbiw r26,23
	adiw r26,24
	st X,r22
	sbiw r26,24
	adiw r26,25
	st X,r23
	sbiw r26,25
	adiw r26,26
	st X,r24
	sbiw r26,26
	adiw r26,27
	st X,r25
.L1469:
	.loc 1 263 0
	ldi r24,lo8(2)
	movw r30,r4
	subi r30,-108
	sbci r31,-1
	st Z,r24
	movw r24,r4
	call inhibit_flag
.LVL1752:
.L1454:
.LBE1199:
.LBE1201:
	.loc 1 428 0
	movw r24,r4
	call inhibit_flag
.LVL1753:
	.loc 1 429 0
	movw r30,r4
	ldd r24,Z+36
	ldd r25,Z+37
	ldd r26,Z+38
	ldd r27,Z+39
	cpi r24,-1
	ldi r31,-1
	cpc r25,r31
	cpc r26,r31
	cpc r27,r31
	brne .+2
	rjmp .L1434
	.loc 1 430 0
	adiw r24,1
	adc r26,__zero_reg__
	adc r27,__zero_reg__
	movw r30,r4
	std Z+36,r24
	std Z+37,r25
	std Z+38,r26
	std Z+39,r27
	.loc 1 431 0
	cp r2,__zero_reg__
	cpc r3,__zero_reg__
	breq .+2
	rjmp .L1488
.L1489:
	ldi r31,lo8(1)
	std Y+11,r31
.LVL1754:
	rjmp .L1430
.LVL1755:
.L1470:
.LBB1202:
.LBB1185:
	.loc 1 278 0
	movw r30,r4
	ldd r24,Z+32
	ldd r25,Z+33
	ldd r26,Z+34
	ldd r27,Z+35
	ldd r18,Y+47
	ldd r19,Y+48
	ldd r20,Y+49
	ldd r21,Y+50
	cp r24,r18
	cpc r25,r19
	cpc r26,r20
	cpc r27,r21
	brlo .+2
	rjmp .L1528
	.loc 1 279 0
	movw r22,r6
	movw r24,r4
	call context_matches
.LVL1756:
	tst r24
	brne .+2
	rjmp .L1529
	.loc 1 280 0
	movw r30,r4
	subi r30,-74
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	call readiness.isra.2
.LVL1757:
	std Y+9,r24
.LVL1758:
	cpse r24,__zero_reg__
	rjmp .L1454
	.loc 1 281 0
	movw r30,r4
	subi r30,-108
	sbci r31,-1
	ld r24,Z
.LVL1759:
	cpi r24,lo8(2)
	breq .+2
	rjmp .L1530
	adiw r30,1
	ld r24,Z
	tst r24
	brne .+2
	rjmp .L1557
	.loc 1 282 0
	cpse r17,__zero_reg__
	rjmp .L1532
	subi r30,22
	sbci r31,-1
	ld r20,Z
	cpse r20,__zero_reg__
	rjmp .L1533
	.loc 1 283 0
	ldi r24,lo8(8)
	movw r30,r28
	adiw r30,1
	movw r26,r30
	0:
	st X+,__zero_reg__
	dec r24
	brne 0b
	.loc 1 284 0
	ldi r24,lo8(1)
	movw r30,r4
	subi r30,-116
	sbci r31,-1
	st Z,r24
	.loc 1 285 0
	movw r30,r4
	ld r26,Z
	ldd r27,Z+1
	adiw r26,4
	ld r10,X+
	ld r11,X
	sbiw r26,4+1
	movw r30,r6
	ldd r18,Z+47
.LVL1760:
.LBB1173:
.LBB1174:
	.loc 1 267 0
	ldd r24,Z+46
.LVL1761:
.L1472:
.LBB1175:
.LBB1176:
	.loc 1 42 0
	cpse r24,__zero_reg__
	rjmp .L1473
.LVL1762:
.LBE1176:
.LBE1175:
	.loc 1 267 0
	ldi r21,0
	subi r20,-22
	sbci r21,-1
	lsl r20
	rol r21
	lsl r20
	rol r21
	add r20,r6
	adc r21,r7
.LBE1174:
.LBE1173:
	.loc 1 285 0
	movw r30,r6
	ldd r22,Z+44
	ldd r23,Z+45
	eor r23,r22
	eor r22,r23
	eor r23,r22
	movw r16,r28
	subi r16,-1
	sbci r17,-1
	ld r24,X+
	ld r25,X
	movw r30,r10
	icall
.LVL1763:
	std Y+9,r24
.LVL1764:
	.loc 1 286 0
	movw r30,r4
	subi r30,-116
	sbci r31,-1
	st Z,__zero_reg__
	.loc 1 287 0
	tst r24
	breq .L1474
.LBE1185:
.LBE1202:
	ldi r31,lo8(11)
.LBB1203:
.LBB1186:
	cpi r24,lo8(23)
	brsh .+2
	rjmp .L1454
.LVL1765:
.L1666:
.LBE1186:
.LBE1203:
	.loc 1 306 0
	std Y+9,r31
	rjmp .L1454
.LVL1766:
.L1473:
.LBB1204:
.LBB1187:
.LBB1180:
.LBB1179:
.LBB1178:
.LBB1177:
	.loc 1 42 0
	mov r25,r24
	andi r25,lo8(1)
	add r20,r25
.LVL1767:
	lsr r24
.LVL1768:
	rjmp .L1472
.LVL1769:
.L1474:
.LBE1177:
.LBE1178:
.LBE1179:
.LBE1180:
	.loc 1 288 0
	ldd r27,Y+5
	std Y+29,r27
	tst r27
	brne .+2
	rjmp .L1534
	ldd r20,Y+1
	ldd r21,Y+2
	ldd r22,Y+3
	ldd r23,Y+4
	cp __zero_reg__,r20
	cpc __zero_reg__,r21
	cpc __zero_reg__,r22
	cpc __zero_reg__,r23
	brlt .+2
	rjmp .L1535
	.loc 1 289 0
	ldd r24,Y+7
.LVL1770:
	cpi r24,lo8(2)
	brlo .+2
	rjmp .L1536
	ldd r24,Y+8
	cpi r24,lo8(33)
	brlo .+2
	rjmp .L1537
	.loc 1 290 0
	ldd r18,Y+6
	.loc 1 289 0
	tst r18
	brne .+2
	rjmp .L1538
	.loc 1 290 0
	mov r24,r18
	andi r24,lo8(-63)
	breq .+2
	rjmp .L1539
	.loc 1 292 0
	movw r30,r6
	ldd r24,Z+46
	cpse r27,r24
	rjmp .L1540
	.loc 1 293 0
	mov r24,r27
	ldi r25,0
	movw r26,r4
	ld r30,X+
	ld r31,X
	ldd r19,Z+16
	rjmp 2f
	1:
	lsr r25
	ror r24
	2:
	dec r19
	brpl 1b
	.loc 1 292 0
	or r24,r25
	breq .+2
	rjmp .L1541
	.loc 1 294 0
	movw r30,r6
	ldd r24,Z+48
	tst r24
	breq .L1475
	movw r30,r4
	subi r30,-74
	sbci r31,-1
	ld r24,Z
	sbrs r24,2
	rjmp .L1542
	andi r18,lo8(24)
	brne .+2
	rjmp .L1543
.L1475:
	.loc 1 297 0
	cp r12,__zero_reg__
	cpc r13,__zero_reg__
	cpc r14,__zero_reg__
	cpc r15,__zero_reg__
	brne .+2
	rjmp .L1544
	cp r20,r12
	cpc r21,r13
	cpc r22,r14
	cpc r23,r15
	brsh .+2
	rjmp .L1545
	ldd r18,Y+55
	ldd r19,Y+56
	ldd r20,Y+57
	ldd r21,Y+58
	ldd r22,Y+59
	ldd r23,Y+60
	ldd r24,Y+61
	ldd r25,Y+62
	ldd r10,Y+36
	ldd r11,Y+37
	ldd r12,Y+38
.LVL1771:
	ldd r13,Y+39
	ldd r14,Y+40
	ldd r15,Y+41
	ldd r16,Y+42
	ldd r17,Y+43
	call __cmpdi2
	brlo .+2
	rjmp .L1546
	movw r18,r10
	movw r20,r12
	movw r22,r14
	movw r24,r16
	ldd r10,Y+30
	ldd r11,Y+31
	ldd r12,Y+32
	ldd r13,Y+33
	ldd r14,Y+34
	ldd r15,Y+44
	ldd r16,Y+45
	ldd r17,Y+46
	call __cmpdi2
	breq .+4
	brlo .+2
	rjmp .L1547
	movw r18,r10
	movw r20,r12
	movw r22,r14
	movw r24,r16
	ldi r26,lo8(-1)
	call __cmpdi2_s8
	brne .+2
	rjmp .L1548
	.loc 1 298 0
	ldd r18,Y+20
	ldd r19,Y+21
	ldd r20,Y+22
	ldd r21,Y+23
	ldd r22,Y+24
	ldd r23,Y+12
	ldd r24,Y+25
	ldd r25,Y+35
	call __cmpdi2_s8
	brne .+2
	rjmp .L1549
	.loc 1 299 0
	movw r26,r4
	adiw r26,12
	ld r27,X
	std Y+26,r27
	movw r30,r4
	ldd r31,Z+13
	std Y+28,r31
	movw r26,r4
	adiw r26,14
	ld r8,X
	sbiw r26,14
	adiw r26,15
	ld r9,X
	sbiw r26,15
	adiw r26,16
	ld r27,X
	movw r30,r4
	ldd r26,Z+17
	ldd r31,Z+18
	std Y+10,r31
	movw r30,r4
	ldd r31,Z+19
	std Y+63,r31
	ldd r18,Y+36
	ldd r19,Y+37
	ldd r20,Y+38
	ldd r21,Y+39
	ldd r22,Y+40
	ldd r23,Y+41
	ldd r24,Y+42
	ldd r25,Y+43
	ldd r10,Y+26
	ldd r11,Y+28
	movw r12,r8
	mov r14,r27
	mov r15,r26
	ldd r16,Y+10
	mov r17,r31
	call __cmpdi2
	breq .+2
	brsh .+2
	rjmp .L1550
	.loc 1 300 0
	ldd r18,Y+55
	ldd r19,Y+56
	ldd r20,Y+57
	ldd r21,Y+58
	ldd r22,Y+59
	ldd r23,Y+60
	ldd r24,Y+61
	ldd r25,Y+62
	call __cmpdi2
	breq .L1476
	brlo .L1476
	call __subdi3
	cpi r18,-1
	sbci r19,-1
	sbci r20,-1
	sbci r21,127
	cpc r22,__zero_reg__
	cpc r23,__zero_reg__
	cpc r24,__zero_reg__
	cpc r25,__zero_reg__
	breq .+4
	brlo .+2
	rjmp .L1551
.L1476:
	.loc 1 301 0
	ldd r18,Y+36
	ldd r19,Y+37
	ldd r20,Y+38
	ldd r21,Y+39
	ldd r22,Y+40
	ldd r23,Y+41
	ldd r24,Y+42
	ldd r25,Y+43
	ldd r10,Y+26
	ldd r11,Y+28
	movw r12,r8
	mov r14,r27
	mov r15,r26
	ldd r16,Y+10
	ldd r17,Y+63
	call __subdi3
	.loc 1 300 0
	cpi r18,-1
	sbci r19,-1
	sbci r20,-1
	sbci r21,127
	cpc r22,__zero_reg__
	cpc r23,__zero_reg__
	cpc r24,__zero_reg__
	cpc r25,__zero_reg__
	breq .+4
	brlo .+2
	rjmp .L1552
	.loc 1 301 0
	ldd r18,Y+30
	ldd r19,Y+31
	ldd r20,Y+32
	ldd r21,Y+33
	ldd r22,Y+34
	ldd r23,Y+44
	ldd r24,Y+45
	ldd r25,Y+46
	ldd r17,Y+63
	call __subdi3
	cpi r18,-1
	sbci r19,-1
	sbci r20,-1
	sbci r21,127
	cpc r22,__zero_reg__
	cpc r23,__zero_reg__
	cpc r24,__zero_reg__
	cpc r25,__zero_reg__
	breq .+4
	brlo .+2
	rjmp .L1553
	.loc 1 303 0
	ldd r18,Y+30
	ldd r19,Y+31
	ldd r20,Y+32
	ldd r21,Y+33
	ldd r22,Y+34
	ldd r23,Y+44
	ldd r24,Y+45
	ldd r25,Y+46
	ldd r10,Y+20
	ldd r11,Y+21
	ldd r12,Y+22
	ldd r13,Y+23
	ldd r14,Y+24
	ldd r15,Y+12
	ldd r16,Y+25
	ldd r17,Y+35
	call __cmpdi2
	breq .L1477
	brlo .L1477
.LVL1772:
.L1478:
.LBE1187:
.LBE1204:
	ldi r31,lo8(16)
	rjmp .L1666
.LVL1773:
.L1477:
.LBB1205:
.LBB1188:
	movw r30,r4
	ldd r10,Z+20
	ldd r11,Z+21
	ldd r12,Z+22
	ldd r13,Z+23
	ldd r14,Z+24
	ldd r15,Z+25
	ldd r16,Z+26
	ldd r17,Z+27
	ldd r18,Y+20
	ldd r19,Y+21
	ldd r20,Y+22
	ldd r21,Y+23
	ldd r22,Y+24
	ldd r23,Y+12
	ldd r24,Y+25
	ldd r25,Y+35
	call __cmpdi2
	breq .+2
	brsh .L1478
	ldd r10,Y+26
	ldd r11,Y+28
	movw r12,r8
	mov r14,r27
	mov r15,r26
	ldd r16,Y+10
	ldd r17,Y+63
	call __cmpdi2
	breq .L1478
	brlo .L1478
	std Y+27,r5
	std Y+26,r4
	movw r12,r4
	ldi r17,0
	ldi r16,0
	.loc 1 304 0
	ldd r31,Y+29
	mov r14,r31
	mov r15,__zero_reg__
.LVL1774:
.L1480:
	movw r24,r14
	mov r0,r16
	rjmp 2f
	1:
	asr r25
	ror r24
	2:
	dec r0
	brpl 1b
	sbrs r24,0
	rjmp .L1479
.LBB1181:
	.loc 1 305 0
	ldd r10,Y+9
	mov r24,r10
	ldi r25,0
	adiw r24,22
	lsl r24
	rol r25
	lsl r24
	rol r25
	add r24,r6
	adc r25,r7
	call get32
.LVL1775:
	.loc 1 306 0
	cp r22,__zero_reg__
	cpc r23,__zero_reg__
	cpc r24,__zero_reg__
	cpc r25,__zero_reg__
	brne .+2
	rjmp .L1554
	movw r26,r12
	adiw r26,40
	ld r8,X+
	ld r9,X+
	ld r10,X+
	ld r11,X
	sbiw r26,40+3
	cp r8,r22
	cpc r9,r23
	cpc r10,r24
	cpc r11,r25
	brlo .+2
	rjmp .L1555
	.loc 1 307 0
	ldd r27,Y+9
	subi r27,lo8(-(1))
	std Y+9,r27
.LVL1776:
.L1479:
	subi r16,-1
	sbci r17,-1
.LVL1777:
	ldi r30,4
	add r12,r30
	adc r13,__zero_reg__
.LBE1181:
	.loc 1 304 0
	cpi r16,8
	cpc r17,__zero_reg__
	brne .L1480
	.loc 1 309 0
	movw r22,r6
	movw r24,r4
	call guard_call
.LVL1778:
	std Y+9,r24
.LVL1779:
	.loc 1 310 0
	tst r24
	breq .L1481
	cpi r24,lo8(23)
	brsh .+2
	rjmp .L1454
.LBE1188:
.LBE1205:
	ldi r16,lo8(11)
.LVL1780:
	rjmp .L1660
.LVL1781:
.L1481:
.LBB1206:
.LBB1189:
	.loc 1 311 0
	movw r24,r4
.LVL1782:
	call sample_clock
.LVL1783:
	movw r30,r4
	subi r30,-74
	sbci r31,-1
	ld r10,Z
	std Y+34,r10
.LVL1784:
	ldd r25,Z+1
	.loc 1 312 0
	mov r24,r10
	call readiness.isra.2
.LVL1785:
	std Y+9,r24
.LVL1786:
	cpse r24,__zero_reg__
	rjmp .L1454
	.loc 1 313 0
	movw r30,r4
	subi r30,-108
	sbci r31,-1
	ld r24,Z
.LVL1787:
	cpi r24,lo8(2)
	breq .+2
	rjmp .L1557
	adiw r30,1
	ld r24,Z
	tst r24
	brne .+2
	rjmp .L1558
	.loc 1 314 0
	movw r22,r6
	movw r24,r4
	call context_matches
.LVL1788:
	tst r24
	brne .+2
	rjmp .L1559
	.loc 1 315 0
	movw r26,r4
	adiw r26,12
	ld r27,X
	std Y+28,r27
	movw r30,r4
	ldd r31,Z+13
	std Y+29,r31
	movw r26,r4
	adiw r26,14
	ld r27,X
	std Y+30,r27
	movw r30,r4
	ldd r31,Z+15
	std Y+31,r31
	movw r26,r4
	adiw r26,16
	ld r27,X
	std Y+32,r27
	movw r30,r4
	ldd r31,Z+17
	std Y+33,r31
	movw r26,r4
	adiw r26,18
	ld r8,X
	sbiw r26,18
	adiw r26,19
	ld r9,X
	sbiw r26,19
	ldd r18,Y+36
	ldd r19,Y+37
	ldd r20,Y+38
	ldd r21,Y+39
	ldd r22,Y+40
	ldd r23,Y+41
	ldd r24,Y+42
	ldd r25,Y+43
	ldd r10,Y+28
	ldd r11,Y+29
	ldd r12,Y+30
	ldd r13,Y+31
	ldd r14,Y+32
	mov r15,r31
	movw r16,r8
.LVL1789:
	call __cmpdi2
	breq .+2
	brsh .+2
	rjmp .L1560
	.loc 1 316 0
	ldd r18,Y+20
	ldd r19,Y+21
	ldd r20,Y+22
	ldd r21,Y+23
	ldd r22,Y+24
	ldd r23,Y+12
	ldd r24,Y+25
	ldd r25,Y+35
	call __cmpdi2
	breq .+2
	brsh .+2
	rjmp .L1478
	adiw r26,20
	ld r10,X
	sbiw r26,20
	adiw r26,21
	ld r11,X
	sbiw r26,21
	adiw r26,22
	ld r12,X
	sbiw r26,22
	adiw r26,23
	ld r13,X
	sbiw r26,23
	adiw r26,24
	ld r14,X
	sbiw r26,24
	adiw r26,25
	ld r15,X
	sbiw r26,25
	adiw r26,26
	ld r16,X
	sbiw r26,26
	adiw r26,27
	ld r17,X
	call __cmpdi2
	breq .+4
	brlo .+2
	rjmp .L1478
	.loc 1 319 0
	adiw r28,86-62
	ldd r20,Y+62
	ldd r21,Y+63
	sbiw r28,86-62
	movw r22,r6
	movw r24,r4
	subi r24,-117
	sbci r25,-1
	call memcpy
.LVL1790:
	movw r30,r4
	subi r30,-110
	sbci r31,-1
	adiw r28,86-63
	ldd r27,Y+63
	sbiw r28,86-63
	st Z,r27
	.loc 1 320 0
	ldd r10,Y+47
	ldd r11,Y+48
	ldd r12,Y+49
	ldd r13,Y+50
	movw r26,r4
	adiw r26,32
	st X+,r10
	st X+,r11
	st X+,r12
	st X,r13
	sbiw r26,32+3
.LVL1791:
.LBE1189:
.LBE1206:
	mov r15,__zero_reg__
.LBB1207:
.LBB1190:
	ldi r17,0
	ldi r16,0
.LVL1792:
.L1483:
	.loc 1 321 0
	movw r30,r6
	ldd r24,Z+46
	ldi r25,0
	mov r0,r16
	rjmp 2f
	1:
	asr r25
	ror r24
	2:
	dec r0
	brpl 1b
	sbrs r24,0
	rjmp .L1482
	.loc 1 322 0
	mov r24,r15
	ldi r25,0
	adiw r24,22
	lsl r24
	rol r25
	lsl r24
	rol r25
	add r24,r6
	adc r25,r7
	call get32
.LVL1793:
	ldd r26,Y+26
	ldd r27,Y+27
	adiw r26,40
	st X+,r22
	st X+,r23
	st X+,r24
	st X,r25
	sbiw r26,40+3
	inc r15
.LVL1794:
.L1482:
	subi r16,-1
	sbci r17,-1
.LVL1795:
	ldd r30,Y+26
	ldd r31,Y+27
	adiw r30,4
	std Y+27,r31
	std Y+26,r30
	.loc 1 321 0
	cpi r16,8
	cpc r17,__zero_reg__
	brne .L1483
	.loc 1 324 0
	ldi r24,lo8(69)
	movw r30,r4
	subi r30,-53
	sbci r31,-2
	movw r26,r30
	0:
	st X+,__zero_reg__
	dec r24
	brne 0b
	.loc 1 325 0
	ldi r25,lo8(1)
	movw r26,r4
	subi r26,-83
	sbci r27,-2
	st X,r25
	movw r26,r6
	adiw r26,46
	ld r24,X
	movw r26,r4
	subi r26,-87
	sbci r27,-2
	st X,r24
	.loc 1 326 0
	ldi r20,lo8(1)
	ldi r21,0
	ldi r22,0
	ldi r23,0
	sbiw r26,10
	st X+,r20
	st X+,r21
	st X+,r22
	st X,r23
	sbiw r26,3
	ldd r27,Y+28
	st Z,r27
	ldd r10,Y+29
	std Z+1,r10
	ldd r11,Y+30
	std Z+2,r11
	ldd r12,Y+31
	std Z+3,r12
	ldd r13,Y+32
	std Z+4,r13
	ldd r14,Y+33
	std Z+5,r14
	std Z+6,r8
	std Z+7,r9
	.loc 1 327 0
	ldi r24,lo8(-1)
	adiw r30,16
	st Z,r24
	std Z+1,r24
	std Z+2,r24
	std Z+3,r24
	std Z+4,r24
	std Z+5,r24
	std Z+6,r24
	std Z+7,r24
	sbiw r30,8
	st Z,r24
	std Z+1,r24
	std Z+2,r24
	std Z+3,r24
	std Z+4,r24
	std Z+5,r24
	std Z+6,r24
	std Z+7,r24
	.loc 1 328 0
	ldd r24,Y+6
	subi r30,-51
	sbc r31,__zero_reg__
	st Z,r24
	.loc 1 329 0
	ldd r24,Y+7
	adiw r30,1
	st Z,r24
	ldd r24,Y+8
	adiw r30,1
	st Z,r24
	sbiw r30,3
	st Z,__zero_reg__
	.loc 1 330 0
	adiw r30,4
	ldd r15,Y+34
.LVL1796:
	bst r15,3
	clr r24
	bld r24,0
	st Z,r24
	.loc 1 331 0
	movw r26,r4
	adiw r26,2
	ld r30,X+
	ld r31,X
	sbiw r30,0
	brne .+2
	rjmp .L1454
.LVL1797:
.LBB1182:
.LBB1183:
	.loc 11 186 0
	ldd r24,Z+4
	cpi r24,lo8(2)
	brne .+2
	rjmp .L1454
	std Z+4,r25
	rjmp .L1454
.LVL1798:
.L1527:
.LBE1183:
.LBE1182:
.LBE1190:
.LBE1207:
	.loc 1 275 0
	ldi r27,lo8(9)
.LVL1799:
.L1668:
	.loc 1 298 0
	std Y+9,r27
	rjmp .L1454
.LVL1800:
.L1528:
	.loc 1 278 0
	ldi r30,lo8(8)
.LVL1801:
.L1667:
	.loc 1 306 0
	std Y+9,r30
	rjmp .L1454
.LVL1802:
.L1529:
	.loc 1 279 0
	ldi r31,lo8(6)
	rjmp .L1666
.LVL1803:
.L1530:
	.loc 1 281 0
	ldi r16,lo8(4)
.LVL1804:
.L1660:
	.loc 1 426 0
	std Y+9,r16
	rjmp .L1454
.LVL1805:
.L1532:
	.loc 1 282 0
	ldi r18,lo8(7)
.LVL1806:
.L1657:
	.loc 1 261 0
	std Y+9,r18
	rjmp .L1454
.LVL1807:
.L1533:
	.loc 1 282 0
	ldi r19,lo8(7)
.LVL1808:
.L1662:
	.loc 1 261 0
	std Y+9,r19
	rjmp .L1454
.LVL1809:
.L1534:
	.loc 1 287 0
	ldi r20,lo8(11)
.LVL1810:
.L1663:
	.loc 1 402 0
	std Y+9,r20
	rjmp .L1454
.LVL1811:
.L1535:
	.loc 1 287 0
	ldi r21,lo8(11)
	rjmp .L1665
.LVL1812:
.L1536:
	ldi r22,lo8(11)
	rjmp .L1661
.L1537:
	ldi r24,lo8(11)
	rjmp .L1658
.L1538:
	ldi r25,lo8(11)
.LVL1813:
.L1664:
	.loc 1 418 0
	std Y+9,r25
	rjmp .L1454
.LVL1814:
.L1539:
	.loc 1 287 0
	ldi r26,lo8(11)
.LVL1815:
.L1669:
	.loc 1 298 0
	std Y+9,r26
.LVL1816:
	rjmp .L1454
.LVL1817:
.L1540:
	.loc 1 293 0
	ldi r27,lo8(12)
	rjmp .L1668
.L1541:
	ldi r30,lo8(12)
	rjmp .L1667
.L1542:
	.loc 1 296 0
	ldi r31,lo8(17)
	rjmp .L1666
.L1543:
	ldi r16,lo8(17)
	rjmp .L1660
.L1544:
	.loc 1 298 0
	ldi r17,lo8(14)
.LVL1818:
.L1659:
	.loc 1 261 0
	std Y+9,r17
	rjmp .L1454
.LVL1819:
.L1545:
	.loc 1 298 0
	ldi r18,lo8(14)
	rjmp .L1657
.LVL1820:
.L1546:
	ldi r19,lo8(14)
	rjmp .L1662
.L1547:
	ldi r20,lo8(14)
	rjmp .L1663
.L1548:
	ldi r21,lo8(14)
	rjmp .L1665
.L1549:
	ldi r22,lo8(14)
	rjmp .L1661
.L1550:
	.loc 1 299 0
	ldi r24,lo8(15)
	rjmp .L1658
.L1551:
	.loc 1 298 0
	ldi r25,lo8(14)
	rjmp .L1664
.L1552:
	ldi r26,lo8(14)
	rjmp .L1669
.L1553:
	ldi r27,lo8(14)
	rjmp .L1668
.LVL1821:
.L1554:
	.loc 1 306 0
	ldi r30,lo8(13)
	rjmp .L1667
.L1555:
	ldi r31,lo8(13)
	rjmp .L1666
.LVL1822:
.L1557:
	.loc 1 313 0
	ldi r17,lo8(4)
	rjmp .L1659
.LVL1823:
.L1558:
	ldi r18,lo8(4)
	rjmp .L1657
.L1559:
	.loc 1 314 0
	ldi r19,lo8(6)
	rjmp .L1662
.LVL1824:
.L1560:
	.loc 1 315 0
	ldi r20,lo8(15)
	rjmp .L1663
.LVL1825:
.L1460:
	.loc 1 408 0
	movw r22,r6
	movw r24,r4
	call reference.lto_priv.15
.LVL1826:
	rjmp .L1658
.L1484:
.LBB1208:
.LBB1209:
	.loc 1 51 0
	subi r24,lo8(-(-3))
.LBE1209:
.LBE1208:
	.loc 1 412 0
	cpi r24,lo8(4)
	brsh .+2
	rjmp .L1485
	movw r16,r4
	subi r16,-84
	sbci r17,-2
	movw r26,r16
	ld r27,X
	std Y+9,r27
.LVL1827:
	cpse r27,__zero_reg__
	rjmp .L1485
	.loc 1 413 0
	movw r24,r4
	call revision
.LVL1828:
	tst r24
	brne .+2
	rjmp .L1485
	movw r30,r4
	subi r30,-113
	sbci r31,-1
	ld r24,Z
	tst r24
	breq .L1561
	ldi r24,lo8(1)
.L1486:
	movw r30,r16
	st Z,r24
	rjmp .L1454
.L1561:
	ldi r24,lo8(3)
	rjmp .L1486
.LVL1829:
.L1522:
	.loc 1 261 0
	ldi r17,lo8(16)
	rjmp .L1659
.LVL1830:
.L1523:
	ldi r18,lo8(16)
	rjmp .L1657
.L1524:
	ldi r19,lo8(16)
	rjmp .L1662
.LVL1831:
.L1526:
	.loc 1 405 0
	ldi r21,lo8(19)
	rjmp .L1665
.L1562:
	.loc 1 418 0
	ldi r22,lo8(7)
	rjmp .L1661
.LVL1832:
.L1563:
	ldi r24,lo8(7)
	rjmp .L1658
.L1564:
	ldi r25,lo8(7)
	rjmp .L1664
.LVL1833:
.L1488:
	.loc 1 432 0
	ldi r24,lo8(1)
	movw r26,r2
	st X,r24
	ldd r24,Y+11
	ori r24,lo8(-128)
	adiw r26,1
	st X,r24
	ldd r20,Y+51
	ldd r21,Y+52
	ldd r22,Y+53
	ldd r23,Y+54
	movw r24,r2
	adiw r24,2
	call put32
.LVL1834:
	ldd r10,Y+9
	movw r30,r2
	std Z+6,r10
	.loc 1 433 0
	adiw r28,100-62
	ldd r12,Y+62
	ldd r13,Y+63
	sbiw r28,100-62
	cp r12,__zero_reg__
	cpc r13,__zero_reg__
	brne .+2
	rjmp .L1489
	.loc 1 434 0
	ldi r24,lo8(7)
	ldi r25,0
	movw r26,r12
	st X+,r24
	st X,r25
	.loc 1 435 0
	cpse r10,__zero_reg__
	rjmp .L1489
	.loc 1 436 0
	ldd r27,Y+11
	cpi r27,lo8(1)
	breq .+2
	rjmp .L1490
.LVL1835:
.LBB1210:
.LBB1211:
	.loc 1 337 0
	movw r20,r2
	subi r20,-7
	sbci r21,-1
	ldi r18,lo8(16)
	ldi r22,0
	movw r24,r4
	call constant_copy
.LVL1836:
	.loc 1 338 0
	movw r20,r2
	subi r20,-23
	sbci r21,-1
	ldi r18,lo8(32)
	ldi r22,lo8(1)
	movw r24,r4
	call constant_copy
.LVL1837:
	.loc 1 339 0
	movw r20,r2
	subi r20,-55
	sbci r21,-1
	ldi r18,lo8(32)
	ldi r22,lo8(2)
	movw r24,r4
	call constant_copy
.LVL1838:
	.loc 1 340 0
	movw r30,r4
	ldd r20,Z+28
	ldd r21,Z+29
	ldd r22,Z+30
	ldd r23,Z+31
	movw r24,r2
	subi r24,-87
	sbci r25,-1
	call put32
.LVL1839:
	movw r14,r4
	ldi r31,72
	add r14,r31
	adc r15,__zero_reg__
	movw r26,r14
	ld r24,X
	adiw r26,1
	ld r25,X
.LVL1840:
.LBB1212:
.LBB1213:
	.loc 1 30 0
	movw r30,r2
	subi r30,-91
	sbci r31,-1
.LVL1841:
	st Z,r25
	adiw r30,1
.LVL1842:
	st Z,r24
.LVL1843:
.LBE1213:
.LBE1212:
	.loc 1 341 0
	movw r26,r2
	subi r26,-93
	sbci r27,-1
	movw r30,r4
	subi r30,-76
	sbci r31,-1
	ldi r24,lo8(32)
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	movw r30,r4
	subi r30,-108
	sbci r31,-1
	ld r24,Z
	movw r30,r2
	subi r30,-125
	sbci r31,-1
	st Z,r24
	movw r30,r4
	subi r30,-74
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
.LVL1844:
.LBB1214:
.LBB1215:
	.loc 1 30 0
	movw r30,r2
	subi r30,-126
	sbci r31,-1
.LVL1845:
	st Z,r25
	adiw r30,1
.LVL1846:
	st Z,r24
.LVL1847:
.LBE1215:
.LBE1214:
	.loc 1 342 0
	movw r26,r4
	ld r30,X+
	ld r31,X
	ldd r24,Z+16
	movw r30,r2
	subi r30,-128
	sbci r31,-1
	st Z,r24
	adiw r30,1
	ldi r24,lo8(72)
	st Z,r24
	adiw r30,1
	ldi r24,lo8(32)
	st Z,r24
	adiw r30,2
	ldd r27,Y+11
	st Z,r27
	sbiw r30,1
	st Z,r27
	.loc 1 343 0
	movw r30,r4
	ldd r16,Z+12
	ldd r17,Z+13
	ldd r18,Z+14
	ldd r19,Z+15
	ldd r20,Z+16
	ldd r21,Z+17
	ldd r22,Z+18
	ldd r23,Z+19
	movw r24,r2
	subi r24,123
	sbci r25,-1
	call put64
.LVL1848:
	movw r26,r4
	adiw r26,20
	ld r16,X
	sbiw r26,20
	adiw r26,21
	ld r17,X
	sbiw r26,21
	adiw r26,22
	ld r18,X
	sbiw r26,22
	adiw r26,23
	ld r19,X
	sbiw r26,23
	adiw r26,24
	ld r20,X
	sbiw r26,24
	adiw r26,25
	ld r21,X
	sbiw r26,25
	adiw r26,26
	ld r22,X
	sbiw r26,26
	adiw r26,27
	ld r23,X
	movw r24,r2
	subi r24,115
	sbci r25,-1
	call put64
.LVL1849:
	movw r30,r4
	ldd r20,Z+32
	ldd r21,Z+33
	ldd r22,Z+34
	ldd r23,Z+35
	movw r24,r2
	subi r24,107
	sbci r25,-1
	call put32
.LVL1850:
	.loc 1 344 0
	movw r30,r4
	subi r30,-87
	sbci r31,-2
	ld r24,Z
	movw r30,r2
	subi r30,103
	sbci r31,-1
	st Z,r24
.LVL1851:
	ldi r31,40
	add r4,r31
	adc r5,__zero_reg__
.LVL1852:
	ldi r16,-102
	add r2,r16
	adc r3,__zero_reg__
.LVL1853:
.L1491:
	.loc 1 345 0
	movw r26,r4
	ld r20,X+
	ld r21,X+
	ld r22,X+
	ld r23,X+
	movw r4,r26
	movw r24,r2
	call put32
.LVL1854:
	ldi r27,4
	add r2,r27
	adc r3,__zero_reg__
	cp r14,r4
	cpc r15,r5
	brne .L1491
.LVL1855:
.LBE1211:
.LBE1210:
	.loc 1 436 0
	ldi r24,lo8(-70)
	ldi r25,0
	adiw r28,100-62
	ldd r30,Y+62
	ldd r31,Y+63
	sbiw r28,100-62
	std Z+1,r25
	st Z,r24
	jmp .L1430
.LVL1856:
.L1490:
	.loc 1 437 0
	ldd r24,Y+11
	subi r24,lo8(-(-16))
	cpi r24,lo8(3)
	brlo .+2
	rjmp .L1492
.LVL1857:
.LBB1216:
.LBB1217:
	.loc 1 349 0
	movw r26,r4
	adiw r26,28
	ld r20,X+
	ld r21,X+
	ld r22,X+
	ld r23,X
	sbiw r26,28+3
	movw r24,r2
	adiw r24,7
	call put32
.LVL1858:
	movw r30,r4
	subi r30,-72
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
.LVL1859:
.LBB1218:
.LBB1219:
	.loc 1 30 0
	movw r30,r2
	std Z+11,r25
	std Z+12,r24
.LVL1860:
.LBE1219:
.LBE1218:
	.loc 1 350 0
	movw r26,r2
	adiw r26,13
	movw r30,r4
	subi r30,-76
	sbci r31,-1
	ldi r24,lo8(32)
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	movw r30,r4
	subi r30,-108
	sbci r31,-1
	ld r24,Z
	movw r26,r2
	adiw r26,45
	st X,r24
	sbiw r26,45
	sbiw r30,34
	ld r24,Z
	ldd r25,Z+1
.LVL1861:
.LBB1220:
.LBB1221:
	.loc 1 30 0
	adiw r26,46
	st X,r25
	sbiw r26,46
	adiw r26,47
	st X,r24
.LVL1862:
.LBE1221:
.LBE1220:
	.loc 1 351 0
	movw r30,r4
	ldd r16,Z+12
	ldd r17,Z+13
	ldd r18,Z+14
	ldd r19,Z+15
	ldd r20,Z+16
	ldd r21,Z+17
	ldd r22,Z+18
	ldd r23,Z+19
	movw r24,r2
	adiw r24,48
	call put64
.LVL1863:
	movw r26,r4
	adiw r26,20
	ld r16,X
	sbiw r26,20
	adiw r26,21
	ld r17,X
	sbiw r26,21
	adiw r26,22
	ld r18,X
	sbiw r26,22
	adiw r26,23
	ld r19,X
	sbiw r26,23
	adiw r26,24
	ld r20,X
	sbiw r26,24
	adiw r26,25
	ld r21,X
	sbiw r26,25
	adiw r26,26
	ld r22,X
	sbiw r26,26
	adiw r26,27
	ld r23,X
	movw r24,r2
	adiw r24,56
	call put64
.LVL1864:
	movw r30,r4
	ldd r20,Z+32
	ldd r21,Z+33
	ldd r22,Z+34
	ldd r23,Z+35
	movw r24,r2
	subi r24,-64
	sbci r25,-1
	call put32
.LVL1865:
	.loc 1 352 0
	movw r30,r4
	subi r30,-87
	sbci r31,-2
	ld r24,Z
	movw r30,r2
	subi r30,-68
	sbci r31,-1
	st Z,r24
.LVL1866:
.LBE1217:
.LBE1216:
	.loc 1 437 0
	ldi r24,lo8(69)
	ldi r25,0
.LVL1867:
.L1670:
	.loc 1 438 0
	adiw r28,100-62
	ldd r26,Y+62
	ldd r27,Y+63
	sbiw r28,100-62
	st X+,r24
	st X,r25
	.loc 1 441 0
	ldi r27,lo8(1)
	std Y+11,r27
.LVL1868:
	jmp .L1430
.LVL1869:
.L1492:
	.loc 1 438 0
	ldd r30,Y+11
	cpi r30,lo8(35)
	brne .+2
	rjmp .L1489
.LVL1870:
.LBB1222:
.LBB1223:
	.loc 1 357 0
	movw r26,r2
	adiw r26,7
	movw r30,r4
	subi r30,-119
	sbci r31,-1
	ldi r24,lo8(42)
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 1 358 0
	ldi r31,-53
	sub r4,r31
	ldi r31,-2
	sbc r5,r31
.LVL1871:
	movw r26,r4
	adiw r26,30
	ld r24,X
	sbiw r26,30
	movw r30,r2
	std Z+49,r24
	adiw r26,31
	ld r24,X
	sbiw r26,31
	std Z+50,r24
	adiw r26,32
	ld r24,X
	sbiw r26,32
	std Z+51,r24
	.loc 1 359 0
	adiw r26,33
	ld r24,X
	sbiw r26,33
	std Z+52,r24
	adiw r26,34
	ld r24,X
	sbiw r26,34
	std Z+53,r24
	adiw r26,35
	ld r24,X
	sbiw r26,35
	std Z+54,r24
	.loc 1 360 0
	adiw r26,28
	ld r24,X
	sbiw r26,28
	adiw r26,29
	ld r25,X
	sbiw r26,29
.LVL1872:
.LBB1224:
.LBB1225:
	.loc 1 30 0
	std Z+55,r25
	std Z+56,r24
.LVL1873:
.LBE1225:
.LBE1224:
	.loc 1 360 0
	adiw r26,24
	ld r20,X+
	ld r21,X+
	ld r22,X+
	ld r23,X
	sbiw r26,24+3
	movw r24,r2
	adiw r24,57
	call put32
.LVL1874:
	.loc 1 361 0
	movw r26,r4
	ld r16,X
	adiw r26,1
	ld r17,X
	sbiw r26,1
	adiw r26,2
	ld r18,X
	sbiw r26,2
	adiw r26,3
	ld r19,X
	sbiw r26,3
	adiw r26,4
	ld r20,X
	sbiw r26,4
	adiw r26,5
	ld r21,X
	sbiw r26,5
	adiw r26,6
	ld r22,X
	sbiw r26,6
	adiw r26,7
	ld r23,X
	movw r24,r2
	adiw r24,61
	call put64
.LVL1875:
	movw r30,r4
	ldd r16,Z+8
	ldd r17,Z+9
	ldd r18,Z+10
	ldd r19,Z+11
	ldd r20,Z+12
	ldd r21,Z+13
	ldd r22,Z+14
	ldd r23,Z+15
	movw r24,r2
	subi r24,-69
	sbci r25,-1
	call put64
.LVL1876:
	movw r26,r4
	adiw r26,16
	ld r16,X
	sbiw r26,16
	adiw r26,17
	ld r17,X
	sbiw r26,17
	adiw r26,18
	ld r18,X
	sbiw r26,18
	adiw r26,19
	ld r19,X
	sbiw r26,19
	adiw r26,20
	ld r20,X
	sbiw r26,20
	adiw r26,21
	ld r21,X
	sbiw r26,21
	adiw r26,22
	ld r22,X
	sbiw r26,22
	adiw r26,23
	ld r23,X
	movw r24,r2
	subi r24,-77
	sbci r25,-1
	call put64
.LVL1877:
	.loc 1 362 0
	movw r30,r4
	ldd r24,Z+36
	movw r30,r2
	subi r30,-85
	sbci r31,-1
	st Z,r24
	movw r26,r4
	adiw r26,36
	ld r20,X
	ldi r21,0
	movw r22,r4
	subi r22,-37
	sbci r23,-1
	movw r24,r2
	subi r24,-86
	sbci r25,-1
	call memcpy
.LVL1878:
	.loc 1 363 0
	movw r30,r4
	ldd r24,Z+36
	ldi r25,0
	subi r24,-86
	sbci r25,-1
	rjmp .L1670
.LVL1879:
.L1500:
.LBE1223:
.LBE1222:
	.loc 1 217 0
	ldi r24,lo8(48)
	ldi r25,0
	jmp .L1442
.LVL1880:
.L1452:
	.loc 1 397 0
	ldd r12,Y+9
	cpse r12,__zero_reg__
	rjmp .L1454
.L1463:
	.loc 1 410 0
	movw r22,r6
	movw r24,r4
	call reference.lto_priv.15
.LVL1881:
	std Y+9,r24
.LVL1882:
	.loc 1 411 0
	cpse r24,__zero_reg__
	rjmp .L1454
	movw r30,r4
	subi r30,-83
	sbci r31,-2
	ld r24,Z
.LVL1883:
	cpi r24,lo8(1)
	breq .+2
	rjmp .L1484
	ldi r20,lo8(1)
	ldi r22,lo8(5)
	movw r24,r4
	call reject_queued
.LVL1884:
	rjmp .L1454
.LVL1885:
.L1441:
.LBB1226:
.LBB1164:
	.loc 1 229 0
	adiw r28,86-62
	ldd r16,Y+62
	ldd r17,Y+63
	sbiw r28,86-62
	cpi r16,72
	cpc r17,__zero_reg__
	brne .+4
	jmp .L1495
	jmp .L1566
.LBE1164:
.LBE1226:
	.cfi_endproc
.LFE174:
	.size	hms_endpoint_handle, .-hms_endpoint_handle
