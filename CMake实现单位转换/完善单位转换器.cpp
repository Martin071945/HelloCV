#include "unitlib.h"

double convert(double value, int type, int unit_from){
    if (type == 1){
        if (unit_from == 1) return value*1.8+32.0;
        if (unit_from == 2) return (value-32.0)/1.8;
    }

    if (type == 2){
        if (unit_from == 1) return value*3.28;
        if (unit_from == 2) return value/3.28;
    }

    if (type == 3){
        if (unit_from == 1) return value/0.453;
        if (unit_from == 2) return value*0.453;
    }
}
