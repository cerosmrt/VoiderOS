cmake_minimum_required(VERSION 3.16)
project(voider_layer)

set(CMAKE_CXX_STANDARD 17)

find_package(Qt6 REQUIRED COMPONENTS Core Gui)
find_package(Python3 REQUIRED COMPONENTS Development)

# layer-shell-qt ships its CMake config as "LayerShellQt" in Qt6 packaging
find_package(LayerShellQt QUIET)
if(NOT LayerShellQt_FOUND)
    find_package(LayerShellQt6 REQUIRED)
endif()

Python3_add_library(voider_layer MODULE voider_layer.cpp)
set_target_properties(voider_layer PROPERTIES OUTPUT_NAME "voider_layer")

target_link_libraries(voider_layer PRIVATE
    Qt6::Core
    Qt6::Gui
    LayerShellQt::Interface
)

install(TARGETS voider_layer LIBRARY DESTINATION lib)
