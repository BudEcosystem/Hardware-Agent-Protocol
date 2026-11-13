set -e; export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq gcc-avr avr-libc simavr >/dev/null 2>&1
cat > t.c <<'C'
#include <avr/io.h>
#include <avr/eeprom.h>
#include <util/delay.h>
static void tx(char c){ while(!(UCSR0A & (1<<UDRE0))); UDR0=c; }
static void say(const char *s){ while(*s) tx(*s++); }
int main(void){
  UCSR0B=(1<<TXEN0); UBRR0=8; DDRB|=(1<<5);
  uint8_t boots = (uint8_t)(eeprom_read_byte((uint8_t*)0)+1); eeprom_write_byte((uint8_t*)0, boots);
  say("HMS-AVR-OK boots="); tx((char)(48 + (boots%10))); tx(10);
  for(uint8_t i=0;i<4;i++){ PORTB^=(1<<5); _delay_ms(5);}
  say("DONE\n");
  for(;;);
}
C
avr-gcc -mmcu=atmega328p -DF_CPU=16000000UL -Os -o t328.elf t.c
avr-gcc -mmcu=atmega2560 -DF_CPU=16000000UL -Os -o t2560.elf t.c
echo "TOOLCHAIN $(avr-gcc --version | head -1)"
echo "SIZE328 $(avr-size t328.elf | tail -1)"
echo "SIZE2560 $(avr-size t2560.elf | tail -1)"
echo "--- run atmega328p"; (timeout 4 simavr -m atmega328p -f 16000000 t328.elf 2>&1 || true) | head -8
echo "--- run atmega2560"; (timeout 4 simavr -m atmega2560 -f 16000000 t2560.elf 2>&1 || true) | head -8
echo "--- cores"; simavr --list-cores 2>&1 | tr '\n' ' ' | head -c 600; echo
