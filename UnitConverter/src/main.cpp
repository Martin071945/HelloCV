#include <iostream>
#include "unitlib.h"

int main(){
    double value;
    int type, unit_from;

    std::cout<<"Enter the converter type:"<<std::endl;
    std::cout<<"1. Temperature"<<std::endl;
    std::cout<<"2. Length"<<std::endl;
    std::cout<<"3. Weight"<<std::endl;
    std::cin>>type;

    std::cout<<"Please enter the value:";
    std::cin>>value;

    if (type == 1){
        std::cout<<"Original Unit (1. Cel 2. Fah)";
        std::cin>>unit_from;
    }
    else if (type == 2){
        std::cout<<"Original Unit (1. Meter 2. Feet)";
        std::cin>>unit_from;
    }
    else if (type == 3){
        std::cout<<"Original Unit (1. Kilo 2. Pound)";
        std::cin>>unit_from;
    }
    else{
        std::cout<<"Invalid type"<<std::endl;
        return 1;
    }

    double result=convert(value, type, unit_from);
    std::cout<<result<<std::endl;
    
    return 0;
}