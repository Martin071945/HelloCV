cmake_minimum_required(VERSION 3.10)
project(UnitConverter)

set(CMAKE_CXX_STANDARD 17)

add_subdirectory(unitlib)
add_executable(main src/main.cpp)
target_link_libraries(main PRIVATE unitlib)
