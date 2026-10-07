#pragma once
#include <iostream>
#include <dlfcn.h>
#include <libgen.h>
#include <string>

namespace CGSim { 

namespace Utilities {

template <class Plugin> class PluginLoader
{
public:

    // Constructor:
    PluginLoader();

    // Destructor:
    ~PluginLoader() = default;

    // load plugin
    std::unique_ptr<Plugin> load(const std::string & pString) const;


    PluginLoader            (const PluginLoader &)=delete;
    PluginLoader & operator=(const PluginLoader &)=delete;

};



template <class Plugin>
PluginLoader<Plugin>::PluginLoader () = default;




template <class Plugin>
std::unique_ptr<Plugin> PluginLoader<Plugin>::load(const std::string & pString) const {
    std::string bNameString = basename((char *) pString.c_str());  // Strip off the directory
    bNameString = bNameString.substr(3);                            // Strip off leading "lib"
    bNameString = bNameString.substr(0, bNameString.find('.'));    // Strip off extensions

    std::string createFunctionName = std::string("create") + bNameString;


    // Loads the library:
    void *handle = dlopen(pString.c_str(), RTLD_NOW);
    if (!handle) {
        std::cerr << dlerror() << std::endl;
        return nullptr;
    }


    // Gets the function
    void *f = dlsym(handle, createFunctionName.c_str());
    if (!f) {
        std::cerr << dlerror() << std::endl;
        return nullptr;
    }

    typedef void *(*CreationMethod) ();
    auto F = (CreationMethod) f;
    auto * factory = (Plugin *) F();
    return std::unique_ptr<Plugin>(factory);
}

}

}